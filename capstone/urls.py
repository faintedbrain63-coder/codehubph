from django.urls import path

from capstone import views

app_name = "capstone"

urlpatterns = [
    path("services/", views.service_list, name="list"),
    path("services/<slug:slug>/", views.project_detail, name="detail"),
    path("services/<slug:slug>/request/", views.request_create, name="request_create"),
    path("projects/request/", views.request_create, name="request_new"),
    # Keep existing project bookmarks and submitted forms working.
    path("capstone/", views.service_list),
    path("capstone/<slug:slug>/", views.project_detail),
    path("capstone/<slug:slug>/request/", views.request_create),
    path("account/capstone/", views.my_requests, name="my_requests"),
    path("account/capstone/<str:reference>/", views.request_detail, name="request_detail"),
    path("account/capstone/<str:reference>/accept/", views.request_accept, name="request_accept"),
    path("account/capstone/<str:reference>/cancel/", views.request_cancel, name="request_cancel"),
    path("account/capstone/<str:reference>/complete/", views.request_complete, name="request_complete"),
    path("account/capstone/<str:reference>/message/", views.request_message, name="request_message"),
    path(
        "account/capstone/<str:reference>/download/<str:kind>/",
        views.request_download,
        name="request_download",
    ),
]
