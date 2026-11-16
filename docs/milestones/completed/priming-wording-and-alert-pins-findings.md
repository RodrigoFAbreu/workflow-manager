# Optional findings: priming-wording-and-alert-pins

| Key | Raised | Finding | Disposition | Reason or link |
| --- | --- | --- | --- | --- |
| F-f33796f5796f | plan LOCAL_MODEL_PLAN_REVIEW round 1 | **PWA-L1-003 -- M4 is in section 3 but not in Flow 6.** Flow 6 runs "M1 to M3", while section 3 lists M4 with a "must fail" (the new J test). Either add M4 to the flow or mark it in section 3 as recorded but not run. | fixed | The checklist's flow 8 now runs M1 to M4 (M4 recorded), matching section 3. |
