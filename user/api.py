from ninja import Router
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from ninja.errors import HttpError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .schemas import (
    ChangePasswordSchema,
    UserCreateSchema,
    UserResponseSchema,
    UserUpdateSchema,
)

router = Router()
User = get_user_model()


@router.post("/register/", response={201: UserResponseSchema}, auth=None)
def register(request, payload: UserCreateSchema):
    email = payload.email.strip().lower()
    candidate = User(
        username=email,
        email=email,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )

    try:
        validate_password(payload.password, candidate)
    except ValidationError as e:
        raise HttpError(400, "; ".join(e.messages))

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=payload.password,
                first_name=payload.first_name,
                last_name=payload.last_name,
            )
        return 201, user

    except IntegrityError:
        raise HttpError(409, "A user with this email already exists.")


@router.get("/me/", response=UserResponseSchema)
def get_profile(request):
    return request.auth


@router.patch("/me/", response=UserResponseSchema)
def update_profile(request, payload: UserUpdateSchema):
    user = request.auth
    changed_fields = []

    if payload.first_name is not None:
        user.first_name = payload.first_name
        changed_fields.append("first_name")
    if payload.last_name is not None:
        user.last_name = payload.last_name
        changed_fields.append("last_name")
    if changed_fields:
        user.save(update_fields=changed_fields)

    if "organization" in payload.model_fields_set:
        user.profile.organization = payload.organization
        user.profile.save()

    return user


@router.post("/me/change_password/", response={200: dict})
def change_password(request, payload: ChangePasswordSchema):
    user = request.auth
    if not user.check_password(payload.current_password):
        raise HttpError(400, "Current password is incorrect.")

    try:
        validate_password(payload.new_password, user)
    except ValidationError as e:
        raise HttpError(400, "; ".join(e.messages))

    user.set_password(payload.new_password)
    user.save(update_fields=["password"])

    return {"detail": "password updated successfully."}
