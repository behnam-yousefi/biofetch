from .orphanet import search_orphanet
from .omim import search_omim
from .disgenet import search_disgenet
from .drugbank import search_drugbank
from .sider import search_sider

TOOLS = [
    search_orphanet,
    search_omim,
    search_disgenet,
    search_drugbank,
    search_sider,
]
RESOURCES = []
PROMPTS = []
