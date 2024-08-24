from __future__ import annotations

from datetime import date, datetime

import pytest

from slumpcone.errors import NotFoundError
from slumpcone.ingest.pipeline import run_ingest
from slumpcone.ingest.profiles import BATCH_RECORDER
from slumpcone.store.db import Database
from slumpcone.store.ingest_repo import IngestRepository
from slumpcone.store.migrations import migrate

GOOD = (
    "ticket,plant,mix,batched,volume\n"
    "881204,PL-1,4000P-57,2024-06-12 07:42,9.0\n"
    "881205,PL-1,4000P-57,2024-06-12 08:15,7.5\n"
)

MIXED = GOOD + ",PL-1,4000P-57,2024-06-12 09:00,nine\n"

RUN_AT = datetime(2024, 6, 13, 8, 0)


@pytest.fixture()
def repo() -> IngestRepository:
    database = Database.in_memory()
    migrate(database)
    return IngestRepository(database)


def load(repo: IngestRepository, text: str = GOOD, name: str = "recorder.csv") -> int:
    result = run_ingest(
        BATCH_RECORDER,
        text,
        name,
        known_digests=repo.known_digests("BATCH-RECORDER"),
        run_at=RUN_AT,
    )
    return repo.record(result)


class CaseRecording:
    def test_a_run_is_written(self, repo: IngestRepository) -> None:
        run_id = load(repo)
        assert run_id > 0
        assert repo.run_count() == 1

    def test_the_counts_are_kept(self, repo: IngestRepository) -> None:
        load(repo, MIXED)
        run = repo.runs_for("BATCH-RECORDER")[0]
        assert run["accepted_count"] == 2
        assert run["quarantined_count"] == 1
        assert run["duplicate_count"] == 0

    def test_the_source_name_is_kept(self, repo: IngestRepository) -> None:
        load(repo, name="june-12.csv")
        assert repo.runs_for("BATCH-RECORDER")[0]["source_name"] == "june-12.csv"

    def test_a_run_with_no_timestamp_gets_one(self, repo: IngestRepository) -> None:
        result = run_ingest(BATCH_RECORDER, GOOD, "recorder.csv")
        repo.record(result)
        assert repo.run_count() == 1


class CaseDigests:
    def test_the_accepted_rows_are_remembered(self, repo: IngestRepository) -> None:
        load(repo)
        assert len(repo.known_digests("BATCH-RECORDER")) == 2

    def test_another_profile_has_its_own_set(self, repo: IngestRepository) -> None:
        load(repo)
        assert repo.known_digests("LAB-BREAKS") == frozenset()

    def test_a_second_load_of_the_same_file_is_all_duplicate(
        self, repo: IngestRepository
    ) -> None:
        load(repo)
        result = run_ingest(
            BATCH_RECORDER,
            GOOD,
            "recorder.csv",
            known_digests=repo.known_digests("BATCH-RECORDER"),
            run_at=RUN_AT,
        )
        assert result.is_all_duplicate
        repo.record(result)
        assert len(repo.known_digests("BATCH-RECORDER")) == 2

    def test_a_new_row_in_a_reloaded_file_lands(self, repo: IngestRepository) -> None:
        load(repo)
        extended = GOOD + "881206,PL-1,4000P-57,2024-06-12 09:10,8.0\n"
        result = run_ingest(
            BATCH_RECORDER,
            extended,
            "recorder.csv",
            known_digests=repo.known_digests("BATCH-RECORDER"),
            run_at=RUN_AT,
        )
        assert result.accepted_count == 1
        repo.record(result)
        assert len(repo.known_digests("BATCH-RECORDER")) == 3


class CaseQuarantine:
    def test_the_refused_rows_come_back(self, repo: IngestRepository) -> None:
        run_id = load(repo, MIXED)
        held = repo.quarantine_for(run_id)
        assert len(held) == 1
        assert held[0].line_number == 4
        assert any("as a number" in reason for reason in held[0].reasons)

    def test_the_raw_values_survive(self, repo: IngestRepository) -> None:
        run_id = load(repo, MIXED)
        assert repo.quarantine_for(run_id)[0].values["volume"] == "nine"

    def test_several_reasons_survive(self, repo: IngestRepository) -> None:
        text = "ticket,plant,mix,batched,volume\n,PL-1,4000P-57,never,nine\n"
        result = run_ingest(BATCH_RECORDER, text, "bad.csv", run_at=RUN_AT)
        run_id = repo.record(result)
        assert len(repo.quarantine_for(run_id)[0].reasons) == 3

    def test_an_unknown_run_is_named(self, repo: IngestRepository) -> None:
        with pytest.raises(NotFoundError, match="99"):
            repo.quarantine_for(99)

    def test_open_quarantine_across_runs(self, repo: IngestRepository) -> None:
        load(repo, MIXED)
        load(repo, MIXED.replace("881205", "881207"))
        held = repo.open_quarantine("BATCH-RECORDER")
        assert len(held) == 2


class CaseHistory:
    def test_runs_for_a_profile_are_newest_first(self, repo: IngestRepository) -> None:
        load(repo, name="first.csv")
        result = run_ingest(
            BATCH_RECORDER,
            GOOD.replace("881204", "881304"),
            "second.csv",
            known_digests=repo.known_digests("BATCH-RECORDER"),
            run_at=datetime(2024, 6, 14, 8, 0),
        )
        repo.record(result)
        assert [run["source_name"] for run in repo.runs_for("BATCH-RECORDER")] == [
            "second.csv",
            "first.csv",
        ]

    def test_runs_between(self, repo: IngestRepository) -> None:
        load(repo)
        assert len(repo.runs_between(date(2024, 6, 13), date(2024, 6, 13))) == 1
        assert repo.runs_between(date(2024, 7, 1), date(2024, 7, 31)) == ()

    def test_forgetting_a_run_releases_its_digests(self, repo: IngestRepository) -> None:
        run_id = load(repo)
        repo.forget_run(run_id)
        assert repo.known_digests("BATCH-RECORDER") == frozenset()
        assert repo.run_count() == 0

    def test_forgetting_takes_the_quarantine_too(self, repo: IngestRepository) -> None:
        run_id = load(repo, MIXED)
        repo.forget_run(run_id)
        assert repo._db.scalar("SELECT count(*) FROM ingest_quarantine") == 0

    def test_forgetting_an_unknown_run_is_named(self, repo: IngestRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.forget_run(99)
