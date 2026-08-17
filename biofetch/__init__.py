from .orphanet import search_orphanet, get_orphanet_disease_details
from .omim import search_omim
from .disgenet import search_disgenet, search_disgenet_enrichment
from .drugbank import search_drugbank
from .sider import search_sider

TOOLS = [
    search_orphanet,
    get_orphanet_disease_details,
    search_omim,
    search_disgenet,
    search_disgenet_enrichment,
    search_drugbank,
    search_sider,
]
RESOURCES = []
PROMPTS = []
