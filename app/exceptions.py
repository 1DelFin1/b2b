from fastapi import HTTPException, status

SELLER_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "NOT_FOUND", "message": "Seller not found"},
)

SELLER_ALREADY_EXISTS = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail={"code": "CONFLICT", "message": "Seller with this email already exists"},
)

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"code": "UNAUTHORIZED", "message": "Authentication required"},
)

INVALID_TOKEN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"code": "UNAUTHORIZED", "message": "Invalid token"},
)

INCORRECT_DATA = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "NOT_FOUND", "message": "Incorrect email or password"},
)

PRODUCT_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "NOT_FOUND", "message": "Product not found"},
)

SKU_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "NOT_FOUND", "message": "SKU not found"},
)

CATEGORY_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "NOT_FOUND", "message": "Category not found"},
)

INVOICE_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "NOT_FOUND", "message": "Invoice not found"},
)
