-- Water soluble chloride content, by mass of the material itself.
--
-- Added rather than back-filled: a material with no figure on file is not a
-- material with no chloride in it, it is one nobody has tested, and the
-- chloride calculation has to be able to tell those apart.

ALTER TABLE material ADD COLUMN chloride_percent REAL;
