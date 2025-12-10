from pydantic import BaseModel
from typing import List
from typing import Optional

# Reuse previously defined base schemas
class AccountConfigurationBase(BaseModel):
    name: str
    value: int

class CreditConfigurationBase(BaseModel):
    standard_name: str
    monthly_credit: int
    margin_up_to: int

# Wrapper schema for POST request
class ConfigurationCreateSchema(BaseModel):
    account_configurations: List[AccountConfigurationBase]
    credit_configurations: List[CreditConfigurationBase]
