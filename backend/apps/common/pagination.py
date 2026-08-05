from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Default 50 per page, but let clients ask for more (up to 500).

    Views that need a whole class or a whole day's register at once — the
    attendance sheet, class lists — pass ?page_size=200. Without
    page_size_query_param DRF silently ignores that and returns only the
    first page.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
