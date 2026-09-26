-- Security fix: Students receive questions through the authenticated backend's
-- explicit safe projection, not direct table reads that could expose private columns.
drop policy if exists questions_student_published on public.questions;
