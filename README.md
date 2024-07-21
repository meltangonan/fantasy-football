## How to update the model with new data
To update the model with the latest data, follow these steps on the <code>dev</code> branch:

### 1. Download Consolidated Excel File
Download the latest consolidated Excel file (`WR_Data`, `RB_Data`) from the repository (from the VS Code explorer). You can save it in your local Downloads folder.

### 2. Download and Integrate Latest Data
Visit [FantasyPros](https://www.fantasypros.com) and download the data for the latest week.
Import the new data into the consolidated Excel file by copy & pasting the data into a new sheet, labeled `Week[#]`.
Save the file.

### 3. Replace File in Repository
Drag and drop the updated Excel file (from the Downloads folder) into the VS Code explorer, replacing the old file in the repository.

### 4. Run Models
Execute the code for all models to incorporate and process the new data.

---

## Cherry picking specific commits

### Checkout the Target Branch
Ensure you're on the <code>main</code> branch, the branch to which you want to apply the changes to

<code>git checkout 'main'</code>

### Cherry-Pick the Commit
Use the git cherry-pick command to apply changes from a specific commit from the <code>dev</code> branch. Replace <code>COMMIT_HASH</code> with the actual commit hash

<code>git cherry-pick COMMIT_HASH</code>

### Complete the Cherry-Pick
Finish the cherry-pick process on VS Code by syncing

---

## If there are conflicts

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
