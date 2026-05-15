"""
Pagination Classes
Shared pagination configuration used by all list endpoints.

Response format:
    {
        "count": 150,
        "total_pages": 6,
        "next": "http://localhost:8000/api/products/?page=3",
        "previous": "http://localhost:8000/api/products/?page=1",
        "results": [ ... ]
    }
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsPagination(PageNumberPagination):
    """
    Default pagination for all list endpoints.
    Frontend can override page_size up to the defined maximum.
    """
    page_size = 25
    page_size_query_param = "page_size"   # ?page_size=50
    max_page_size = 100
    page_query_param = "page"             # ?page=2

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "total_pages": self.page.paginator.num_pages,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        })

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "total_pages": {"type": "integer"},
                "next": {"type": "string", "nullable": True},
                "previous": {"type": "string", "nullable": True},
                "results": schema,
            },
        }


class LargeResultsPagination(PageNumberPagination):
    """
    Used for analytics endpoints where larger datasets are returned at once,
    such as monthly trend data or product performance lists.
    """
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500
