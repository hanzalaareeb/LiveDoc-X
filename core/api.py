from ninja import Router

router = Router()


@router.get("/health", auth=None)
def health(request):
    return {"status": "core OK"}
