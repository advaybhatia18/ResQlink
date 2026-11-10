
#ifndef EMERGENCY_H
#define EMERGENCY_H

#ifdef _WIN32
#define RESQLINK_API __declspec(dllexport)
#else
#define RESQLINK_API
#endif

RESQLINK_API int calculate_priority(int severity);
RESQLINK_API const char* severity_label(int severity);

#endif
