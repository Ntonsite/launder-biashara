from pydantic import BaseModel, Field
class LoginRequest(BaseModel): email:str=Field(min_length=5,max_length=255); password:str=Field(min_length=8,max_length=128)
class TokenResponse(BaseModel): access_token:str; token_type:str="bearer"; user:dict
class BusinessRegisterRequest(BaseModel):
    full_name:str=Field(min_length=2,max_length=120); business_name:str=Field(min_length=2,max_length=160); phone:str=Field(min_length=9,max_length=20); email:str=Field(min_length=5,max_length=255); password:str=Field(min_length=8,max_length=128)
