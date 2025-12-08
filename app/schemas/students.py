from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date, time

class StudentCreateRequest(BaseModel):
    profile_image:Optional[str]=None
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
    pickup_point: Optional[str] = None
    pickup_time: Optional[str] = None
    drop_point: Optional[str] = None
    drop_time: Optional[str] = None
    # school_id: str

class StudentUpdateRequest(BaseModel):
    profile_image: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[date] = None
    class_id: Optional[int] = None
    section_id: Optional[int] = None
    is_transport: Optional[bool] = None
    driver_id: Optional[int] = None
    pickup_point: Optional[str] = None
    pickup_time: Optional[str] = None
    drop_point: Optional[str] = None
    drop_time: Optional[str] = None

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

# ---------------- Parent ----------------
class ParentUpdate(BaseModel):
    parent_name: Optional[str] = None
    relation: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    occupation: Optional[str] = None
    organization: Optional[str] = None

# ---------------- Address Base ----------------
class AddressBaseUpdate(BaseModel):
    enter_pin: Optional[str] = None
    division: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    building: Optional[str] = None
    house_no: Optional[str] = None
    floor_name: Optional[str] = None

# ---------------- Present Address ----------------
class PresentAddressUpdate(AddressBaseUpdate):
    is_this_permanent_as_well: Optional[bool] = None

# ---------------- Permanent Address ----------------
class PermanentAddressUpdate(AddressBaseUpdate):
    pass

# ---------------- Wrapper ----------------
class ParentWithAddressUpdate(BaseModel):
    parent: Optional[ParentUpdate] = None
    present_address: Optional[PresentAddressUpdate] = None
    permanent_address: Optional[PermanentAddressUpdate] = None

class SelfSignedStudentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    profile_image: Optional[str] = None
    select_board: Optional[str] = None
    select_class: Optional[int] = None
    school_name: Optional[str] = None
    school_location: Optional[str] = None

    pin: Optional[int] = None
    division: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    plot: Optional[str] = None