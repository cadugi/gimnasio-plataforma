# SDD ledger — plan: /home/ubuntu/work/docs-altas/2026-10-20-bajas-mantenimiento-prorrateo-plan.md
Setup: no git repo. Working copy /home/ubuntu/work/bajas-src (PHP from recovery-6326, assets from current); pristine copy /home/ubuntu/work/bajas-orig for diffs/sha checks.
Ruling: "commit" steps replaced by green test runs + final deploy with backups — no git on server — cost if wrong: none, backups cover rollback.
Pre-flight: T2,T5 consume T1 prorateMonth/withdrawalDates/maintenanceMonths; T4,T5,T6 consume T3 withdrawals table + session API. Names consistent across Interfaces blocks.
Task 1: complete (tests: run.sh t1_proration.php → PASS 17/17)
Task 2: complete (tests: run.sh t2_alta_prorrateo.php → PASS 6/6; pdfcheck PASS; node t2_js.js PASS)
Task 3: complete (tests: run.sh t3_bajas.php → PASS 31/31; pdfcheck baja+mantenimiento PASS). API routes wired; HTTP flow verified in Task 6 via local server.
Task 4: Ruling: buildWithdrawalEmail gains $lastDay param (plan signature lacked it; email must say until when they can train) — cost if wrong: none.
Task 4: Ruling: test subject regex fixed (captured trailing \r) — test bug, not code.
Task 4: complete (tests: run.sh t4_correo_baja.php → PASS 9/9). Worker loop verified by php -l; real send verified at deploy.
Task 5: complete (tests: run.sh t5_admin_bajas.php → PASS 25/25; full suite t1-t5 PASS). Ruling: list method named withdrawalList (plan said withdrawals) — clearer, avoids clash with table name — cost: none. Ruling: return month is charged at reception; dues resume the month after return — avoids double charge — cost if wrong: one month of manual charge.
Task 6: complete (tests: e2e/flow.js headless Chromium — tablet maintenance flow for paper member + panel accept + return quote 42,08 € → OK, 0 JS errors; screenshots reviewed with client.css). Ruling: admin-withdrawals.js loaded only outside client portal.
Final: self-review (no subagent tool used: user did not ask for subagents). Final: fixed stale month between review and sign — t6_fechas_caducadas RED→GREEN, suite 6/6 files PASS.
