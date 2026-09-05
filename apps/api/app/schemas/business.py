from typing import Any
from pydantic import BaseModel,Field
class OnboardingUpdate(BaseModel):step:int=Field(ge=1,le=9);data:dict[str,Any];completed:bool=False
class ServiceCreate(BaseModel):name:str=Field(min_length=2,max_length=120);description:str="";pricing_model:str="PER_ITEM";price:int=Field(ge=0);turnaround_hours:int=Field(default=24,gt=0);active:bool=True
class CustomerCreate(BaseModel):name:str=Field(min_length=2,max_length=120);phone:str=Field(min_length=9,max_length=20);email:str|None=None
class BusinessOrderCreate(BaseModel):customer_name:str=Field(min_length=2);phone:str=Field(min_length=9);source:str="WALK_IN";total:int=Field(gt=0);notes:str=""
