-- The two indexes the query plans said were missing.
--
-- This migration exists because the probe set in store/timing.py was written
-- and run against a seeded register. Eight of the ten queries it watches were
-- already searching an index. Two were not, and both of them were the same
-- mistake: a composite index whose leading column is not the one the query
-- filters on.
--
-- The ticket table had three indexes and every one of them led with something
-- else -- the plant, the mixture, the job -- with the batch time second. The
-- daily page does not filter on any of those. It asks for a window of time
-- across the whole plant, which is the first query every report runs, and it
-- was reading the ticket table whole.
--
-- The certificate table had the same shape: an index leading with the material
-- code, right for "what certificates does this cement have" and useless for
-- "what expires before March", which is what the compliance calendar asks.
--
-- Nothing else is added here. Every other probe already reported SEARCH, and
-- an index no query uses is a write cost on every insert in exchange for
-- nothing.

CREATE INDEX ticket_by_date ON batch_ticket (batched_at);
CREATE INDEX certificate_by_expiry ON material_certificate (expires);
