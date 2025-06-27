import os
import subprocess
import glob
import datetime
import time
from pathlib import Path
DAYS = 30
MINUTES = (DAYS * 24) * 60
DAYS_DLS = 1
MINUTES_DLS = (DAYS_DLS * 24) * 60

def prune(dry = False):
    return_text = "dontremove is protecting the following files:\n"
    date_stamped = False
    files = glob.glob('/media/**',recursive = True) 
    for file in files:
        if "/media/drive" in file or "/media/jaxuploads/" in file or "dontremove" in file or "dontmove" in file or "protected.log" in file:
            continue
        try:
            file = Path(file)
            if not file.is_file():
                print(file)
                continue
            creation_time = os.path.getctime(file)  

      # Get the current time.
            time_now = time.time()  

      # Calculate the difference between the two times in minutes.
            age_in_minutes = (time_now - creation_time) / 60
            age_in_minutes = round(age_in_minutes, 0)
            delete = False
            if age_in_minutes > MINUTES:
                delete = True
                with open("/media/dontremove", "r") as f:
                    lines = f.readlines()
                    for line in lines:
                        line = line.split(";")[0]
                        if line.lower().replace("\n", "").strip() in str(file).lower().replace(".", " ").replace("-", "").strip():
                            if dry:
                                return_text += f"{file}\n"
                            delete = False
                            break
            if delete:
                with open ("/media/deleted.log", "a") as f:
                    age_in_days = age_in_minutes / 1440
                    age_in_days_remainder = age_in_minutes % 1440
                    remainder_in_hours = age_in_days_remainder / 60
                    remainder_in_minutes = age_in_days_remainder % 60
                    if not date_stamped:
                        f.write(f"\n\n{datetime.datetime.now()}:\n")
                        date_stamped = True
                    f.write(f"{file}, age: {round(age_in_days)} days, {round(remainder_in_hours)} hours, {round(remainder_in_minutes)} minutes\n")
                    print(f"{file}, age: {round(age_in_days)} days, {round(remainder_in_hours)} hours, {round(remainder_in_minutes)} minutes")
                print(f"Deleting {file}")
                if not dry:
                    os.remove(file)
    
        except Exception as e:
            print(e)
    output = subprocess.getoutput("rm -rf /media/downloads/complete/* && rm -rf /media/downloads/incomplete/*")
    if dry:
        return return_text

prune()
