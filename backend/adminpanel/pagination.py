from rest_framework.pagination import PageNumberPagination


class AdminListPagination(PageNumberPagination):
    """Bounds the three genuinely unbounded, system-wide admin list views
    (every user, every user's tasks, every task across every user) -- see
    SECURITY.md's pagination section. `page_size` is set well above any
    realistic near-term row count on purpose: the existing admin UI pages
    (Admin.jsx, AdminTasks.jsx) already do their own client-side slicing/
    display on top of whatever comes back in one response, so this exists
    to put a hard ceiling on response size, not to introduce new page-
    navigation UI. `page_size_query_param` lets a future paginated UI ask
    for a specific page without a backend change; `max_page_size` stops a
    client from requesting its way back to "everything, unbounded" via
    ?page_size=999999.
    """

    page_size = 500
    page_size_query_param = "page_size"
    max_page_size = 1000
