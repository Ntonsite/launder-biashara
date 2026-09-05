from pydantic import BaseModel, Field
class OrderCreate(BaseModel):
    customer_name:str=Field(min_length=2,max_length=120); phone:str=Field(min_length=9,max_length=20); laundry_slug:str; fulfillment_method:str="PICKUP"; payment_method:str="MOBILE_MONEY"; total:int=Field(gt=0)
