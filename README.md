# fantasy-football

1. Download the consolidated Excel file from the repo (this can just be on your local <code>Downloads</code> folder).
2. Download the latest weeks individual data from fantasypros.com and copy it into the consolidated Excel file.
4. Copy & replace the file into the repo (open <code>'Downloads'</code> folder in local file explorer and drag it over to the VS explorer)
6. Run the code for all models.

---

## How to push and merge changes from <code>'main'</code> to <code>'week-#'</code> branches

### Checkout the Target Branch
Ensure you're on the branch to which you want to apply the changes

<code>git checkout week-#</code>

### Cherry-Pick the Commit
Use the git cherry-pick command to apply changes from a specific commit in the main branch. Replace COMMIT_HASH with the actual commit hash

<code>git cherry-pick COMMIT_HASH</code>

### Accept Changes from the main Branch
To accept all changes from the main branch for the conflicted files, use:

<code>git checkout --theirs "WR Model.ipynb"</code>

<code>git checkout --theirs "RB Model.ipynb"</code>

### Mark the Files as Resolved
After resolving conflicts, inform Git that the conflicts are addressed

<code>git add "WR Model.ipynb"</code>

<code>git add "RB Model.ipynb"</code>

### Run the updated files
Open the files, run all cells, and save the files to ensure the model is refreshed using the target branches data

### Complete the Cherry-Pick
With conflicts resolved, finish the cherry-pick process on VS Code by commiting and syncing
