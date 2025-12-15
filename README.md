# Recover BORIS project file
We had a `.boris` project file corrupted in the lab - completely empty. But we had a `.csv` file with all the events from the project, so we decided to try and recover the lost project file as all the data was still there. And this is the result, a Python script - we successfully recovered the BORIS project file!

# User guide
1. Ensure you have a working Python installation.
2. Save the `boris-recovery.py` file
3. From the command-line (Powershell on Windows), move to the folder where you saved `boris-recovery.py` file (*e.g.* `cd PATH/TO/SCRIPT`)
4. From there, run `python boris-recovery.py path/to/your/csv/file.csv` 
5. You should now have a fully functional `.boris` file next to the `.csv` file!