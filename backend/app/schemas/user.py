from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenRefresh(BaseModel):
    refresh_token: str

class TokenPayload(BaseModel):
    sub: Optional[int] = None
    refresh: bool = False
    impersonator_id: Optional[int] = None

class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = True
    full_name: Optional[str] = None

class UserCreate(UserBase):
    email: EmailStr
    password: str

class UserUpdate(UserBase):
    password: Optional[str] = None


class PermissionSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RoleSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    permissions: List[PermissionSchema] = []

    model_config = ConfigDict(from_attributes=True)


class UserRead(UserBase):
    id: int
    is_superuser: bool
    roles: List[RoleSchema] = []
    is_impersonated: bool = False
    manager_id: Optional[int] = None
    phone: Optional[str] = None
    location: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserLinkRead(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permission_ids: List[int] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[List[int]] = None


class UserAdminUpdate(UserBase):
    role_ids: Optional[List[int]] = None
    password: Optional[str] = None
    manager_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class UserRolesUpdate(BaseModel):
    role_ids: List[int]
