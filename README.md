# Postman REPL

Postman repl uses IPython to present the user with an interface to communicate with APIs.
It loads postman configuration data into global state, allowing for quick and easy
communication with an API.

# Loading

* You can load middleware, environments, and requests through command line flags
* You can load new collections at runtime using the load_collection function
* You can load new environments at runtime using the load_environment function
* You can load middleware by calling load_middleware

# Requests

* Requests are loaded into global P variable. TAB COMPLETION HELPS!
* Requests are namespaced under there folder name.
* You can simply call the request with no args to use the default parameters from the Postman config
* Requests use the "requests" library.  You can pass the kwargs for the request.
* You can pass an environment to the requests, or it will use the global "E" environment
* Returns the response

# Middleware

* Middleware is stored in global MW variable
* Middleware will be called when there is a foldername_request name match
   * For example, if you have a folder "authentication" and a request "authenticate", your middleware function name should be authentication_authenticate
   * Having no folder is supported, it would just be request name (for example: "authenticate")
* Middleware should be defined in a separate python module
* Middleware is a function that takes 3 parameters
    * The function to run the request, taking a single argument for the kwargs
    * The kwargs that will be ran in the run function
    * The env that the run function will use
* After request, some global variables are set
    * R holds the response
    * D holds the data
    * J holds the data, parsed as JSON

# History

* The global H variable holds the history
* You can see the history by calling H()
* You can rerun a history call by calling H(index)
* You can inspect the history with H.history
* Each history has the response, data, and JSON data attached to it

# TODO

* Support for other serialization formats besides JSON
* Add auth support
* Investigate postman unsupported features
