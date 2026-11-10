
#include "emergency.h"

int calculate_priority(int severity)
{
    if (severity < 1 || severity > 5)
    {
        return -1;
    }

    return severity * 20;
}

const char* severity_label(int severity)
{
    switch (severity)
    {
        case 1: return "LOW";
        case 2: return "MODERATE";
        case 3: return "HIGH";
        case 4: return "VERY HIGH";
        case 5: return "CRITICAL";
        default: return "INVALID";
    }
}
