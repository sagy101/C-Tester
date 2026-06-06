# Privacy History Scrub Runbook

Use this only when the repository owner decides to remove private assignment data from reachable Git history. This changes commit IDs. Coordinate with every collaborator before pushing rewritten history.

## Private Data Policy

Treat these as private unless they are explicit public examples under `examples/`:

- `Q*/input.txt`
- `Q*/original_sol.c`
- `Q*/C/<student-id>.c`
- generated grades, outputs, Excel files, archives, PDFs, repair artifacts, and `submit_error.txt`

## Safe Workflow

1. Freeze pushes to `master`.
2. Record the current remote state:
   ```powershell
   git ls-remote origin > pre-privacy-scrub-refs.txt
   ```
3. Create a local backup mirror outside the working repo:
   ```powershell
   git clone --mirror https://github.com/sagy101/C-Tester.git C-Tester.backup.git
   ```
4. Create a separate scrub mirror:
   ```powershell
   git clone --mirror https://github.com/sagy101/C-Tester.git C-Tester.scrub.git
   cd C-Tester.scrub.git
   ```
5. Install `git-filter-repo` if needed:
   ```powershell
   python -m pip install git-filter-repo
   ```
6. Remove private paths from all history. Start with known paths, then rerun the privacy audit until clean:
   ```powershell
   git filter-repo --force `
     --path Q1/input.txt --path Q1/original_sol.c `
     --path Q2/input.txt --path Q2/original_sol.c `
     --path Q3/input.txt --path Q3/original_sol.c `
     --path Q1/original_sol_output.txt `
     --path submit_error.txt `
     --path-glob "*.xlsx" `
     --path-glob "*.zip" `
     --path-glob "*.rar" `
     --path-glob "*.pdf" `
     --path-glob "Q*/C/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].c" `
     --path-glob "Q*/llm_fixed/**" `
     --path-glob "Q*/llm_fixed_output/**" `
     --invert-paths
   ```
7. Verify the scrubbed mirror in a fresh clone before pushing:
   ```powershell
   git clone C-Tester.scrub.git C-Tester.verify
   cd C-Tester.verify
   python tools/privacy_audit.py master
   python tools/privacy_audit.py master --history
   python -m compileall -q c_tester tests
   python -m unittest discover -s tests -p "test_*.py"
   ```
8. Only the repository owner should publish the rewritten `master`, using lease protection:
   ```powershell
   git push --force-with-lease origin master
   ```

Do not use a plain force push. Do not push backup tags that keep private objects reachable on the remote.

## Recovery

If the scrubbed remote is wrong, restore from the local `C-Tester.backup.git` mirror. Keep that backup offline/private until the team confirms the scrubbed repository is healthy.
