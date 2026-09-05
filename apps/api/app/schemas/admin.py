from pydantic import BaseModel
class MarketplaceDecision(BaseModel): reason:str|None=None
