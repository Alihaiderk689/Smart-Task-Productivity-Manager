from rest_framework.pagination import PageNumberPagination


class DefaultListPagination(PageNumberPagination):
    """Bounds the user-facing list endpoints that previously had no ceiling
    at all (tasks, categories -- see SCALABILITY.md's pagination section,
    H1). `page_size` is generous relative to a typical per-user dataset
    ("fine at dozens of tasks") so this doesn't change the single-request
    UX for realistic sizes -- it just puts a hard ceiling on response size
    for the pathological case (heavy daily-repeat-series users). Mirrors
    adminpanel/pagination.py's AdminListPagination, same rationale, smaller
    numbers since this is per-user data, not cross-user.
    """

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500
