from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserPublic(ORMModel):
    id: int
    email: EmailStr
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    is_active: bool = True


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8)
    is_active: bool | None = None


class RolePublic(ORMModel):
    id: int
    name: str
    created_at: dt.datetime
    updated_at: dt.datetime


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class RoleUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class PermissionPublic(ORMModel):
    id: int
    code: str
    description: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class PermissionCreate(BaseModel):
    code: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=255)


class PermissionUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=255)


class AssignRolesRequest(BaseModel):
    role_ids: list[int]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthUser(BaseModel):
    id: int
    email: EmailStr


class MeResponse(BaseModel):
    user: AuthUser
    permissions: list[str]


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUser
    permissions: list[str]


class LogoutResponse(BaseModel):
    status: str
