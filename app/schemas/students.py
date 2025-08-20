from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date, time

class StudentCreateRequest(BaseModel):
    first_name: str
    last_name: str
    gender: str
    dob: date
    email: EmailStr
    roll_no: int
    class_id: int
    section_id: int
    is_transport: bool = True
    driver_id: Optional[int] = None
    # school_id: str
    
class AddressBase(BaseModel):
    enter_pin: str
    division: Optional[str] = None
    district: str
    state: str
    country: str
    building: Optional[str] = None
    house_no: Optional[str] = None
    floor_name: Optional[str] = None

class PresentAddressCreate(AddressBase):
    is_this_permanent_as_well: bool = False

class PermanentAddressCreate(AddressBase):
    pass

class ParentCreate(BaseModel):
    parent_name: str
    relation: str 
    phone: str
    email: EmailStr
    occupation: Optional[str] = None
    organization: Optional[str] = None

class ParentWithAddressCreate(BaseModel):
    parent: ParentCreate
    present_address: PresentAddressCreate
    permanent_address: Optional[PermanentAddressCreate] = None    