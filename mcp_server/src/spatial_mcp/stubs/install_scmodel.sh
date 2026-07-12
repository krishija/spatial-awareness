curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

cd /home/ec2-user/SageMaker

git clone https://github.com/czbiohub-chi/scldm_cd4.git
cd scldm_cd4
chmod +x ./init.sh

./init.sh

source /home/ec2-user/SageMaker/scldm_cd4/venv/scldm_cd4/bin/activate
python -m ipykernel install --user --name scldm_cd4 --display-name "Python (scldm_cd4)"

wget -O hgnc_genes.txt "https://www.genenames.org/cgi-bin/download/custom?col=gd_app_sym&col=md_ensembl_id&status=Approved&hgnc_dbtag=on&order_by=gd_pub_ensembl_id&format=text&submit=submit"

uv pip install gseapy

uv pip install huggingface_hub

mkdir /home/ec2-user/SageMaker/biohub_model/

# download the repo (adjust repo id/type if it's a model vs dataset repo)
hf download biohub/scldm_cd4 --local-dir /home/ec2-user/SageMaker/biohub_model/