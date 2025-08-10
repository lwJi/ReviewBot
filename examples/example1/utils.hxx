// example1/utils.hxx
#ifndef UTILS_HXX
#define UTILS_HXX

#include <string>

// Using a C-style macro is not modern C++
#define MAX_USERS 100

// Global variables are generally bad practice and can lead to bugs.
std::string last_error_message;

void logError(std::string message) {
  // This function has side effects by modifying a global variable.
  last_error_message = message;
}

#endif // UTILS_HXX
