"""Read SENTINEL tables (tables/<name>/<split>/part-*.csv.gz) from the tables folder or straight out of the zip."""
import glob
import io
import os
import zipfile

import pandas as pd


def read_table(data_path, name, splits=None, usecols=None):
    """Return one table as a DataFrame. splits=None reads every split folder (train, validation, ..., all)."""
    def wanted(path):
        parts = path.replace("\\", "/").split("/")
        if name not in parts or not path.endswith(".csv.gz"):
            return False
        split = parts[parts.index(name) + 1]  # the folder right after the table name
        return splits is None or split in splits

    frames = []
    if data_path.lower().endswith(".zip"):
        with zipfile.ZipFile(data_path) as z:
            for n in sorted(x for x in z.namelist() if wanted(x)):
                frames.append(pd.read_csv(io.BytesIO(z.read(n)), compression="gzip", usecols=usecols, low_memory=False))
    else:
        # only .csv.gz: the tables folder also holds some extracted .csv copies that would load rows twice
        for f in sorted(glob.glob(os.path.join(data_path, name, "*", "*.csv.gz"))):
            if wanted(f):
                frames.append(pd.read_csv(f, usecols=usecols, low_memory=False))
    if not frames:
        raise SystemExit(f"No {name}/*/part-*.csv.gz under {data_path}. Set DATA_PATH to the tables folder or the zip.")
    return pd.concat(frames, ignore_index=True)
