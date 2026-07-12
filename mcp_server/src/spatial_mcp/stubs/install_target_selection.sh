conda env create -f environment_full.yml

# Activate it
conda init bash
source ~/.bashrc

conda activate atera

# Register it as a Jupyter kernel (optional, for notebook use)
python -m ipykernel install --user --name atera --display-name "Python (atera)"