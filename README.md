# fantasy-football

1. Each week, create a new branch, <code>'week-#'</code>, from <code>'main'</code>.
2. Download csv file from FanatsyPros with the updated data from the new week. This can just be downloaded into local <code>'Downloads'</code> folder.
3. Ensure that the name of the csv file matches the original csv file (from <code>'main'</code>) name.
4. Copy the file into the new branch (open <code>'Downloads'</code> folder in local file explorer and drag it over to the VS explorer)
5. Replace the file. If necessary, rename the file to match the original name.
6. Run the code.

---

## How to push and merge changes from <code>'main'</code> to <code>'week-#'</code> branches

### Checkout the Target Branch:
Ensure you're on the branch to which you want to apply the changes

<code>git checkout week-#</code>

### Cherry-Pick the Commit:
Use the git cherry-pick command to apply changes from a specific commit in the main branch. Replace COMMIT_HASH with the actual commit hash

<code>git cherry-pick COMMIT_HASH</code>

### Accept Changes from the main Branch:
To accept all changes from the main branch for the conflicted files, use

<code>git checkout --theirs "WR Model.ipynb"</code>

<code>git checkout --theirs "RB Model.ipynb"</code>

### Mark the Files as Resolved:
After resolving conflicts, inform Git that the conflicts are addressed

<code>git add "WR Model.ipynb"</code>

<code>git add "RB Model.ipynb"</code>

### Complete the Cherry-Pick:
With conflicts resolved, finish the cherry-pick process

<code>git cherry-pick --continue</code>

### Push the Changes to the Remote Repository:
If desired, update the remote repository with the resolved changes

<code>git push origin week-6</code>