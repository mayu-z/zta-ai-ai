from datetime import datetime

from pydantic import BaseModel, Field


class GoogleAuthRequest(BaseModel):
    google_token: str = Field(min_length=3)


class OIDCAuthRequest(BaseModel):
    id_token: str = Field(min_length=20)


class MFATOTPVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class AuthUser(BaseModel):
    id: str
    email: str
    name: str
    persona: str
    department: str | None = None


class AuthResponse(BaseModel):
    jwt: str
    user: AuthUser


class RefreshRequest(BaseModel):
    jwt: str


class RefreshResponse(BaseModel):
    jwt: str


class LogoutResponse(BaseModel):
    message: str


class MFATOTPEnrollResponse(BaseModel):
    method: str
    secret: str
    otpauth_uri: str


class MFATOTPVerifyResponse(BaseModel):
    jwt: str
    mfa_verified: bool


class ErrorResponse(BaseModel):
    error: str
    code: str
    timestamp: datetime
