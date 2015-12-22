#!/usr/bin/python
"""
Script for starting a repl with postman configs/env loaded.
"""


import argparse
import json
import pprint
import re
import sys
import copy
from urllib.parse import urlparse, parse_qs
import importlib.machinery
import IPython
from jinja2 import Template
import requests


class O(object):
    """
    O allows for accessing object properties using dot notation
    or index notation.
    Useful for tab completion and ease of use in IPython.
    All instance methods defined with a leading '_' to aid in use of tab completion
    Modified from: http://www.adequatelygood.com/JavaScript-Style-Objects-in-Python.html
    """

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __getitem__(self, name):
        return self.__dict__.get(name, None)

    def __setitem__(self, name, val):
        return self.__dict__.__setitem__(name, val)

    def __delitem__(self, name):
        if name in self.__dict__:
            del self.__dict__[name]

    def __getattr__(self, name):
        return self.__getitem__(name)

    def __setattr__(self, name, val):
        return self.__setitem__(name, val)

    def __delattr__(self, name):
        return self.__delitem__(name)

    def __iter__(self):
        return self.__dict__.__iter__()

    def __repr__(self):
        return pprint.pformat(self._to_dict_recursive(), width=4)

    def __str__(self):
        return self.__dict__.__str__()

    def _to_dict(self):
        return self.__dict__.copy()

    def _to_dict_recursive(self):
        """ Recursively converts all Os to dicts """
        def handle_list(l):
            out = []
            for x in l:
                if isinstance(x, O):
                    out.append(x._to_dict_recursive())
                elif isinstance(x, (list, tuple)):
                    out.append(handle_list(x))
                else:
                    out.append(copy.copy(x))
            return out

        newDict = {}
        for k, v in self.__dict__.items():
            if isinstance(v, O):
                newDict[k] = v._to_dict_recursive()
            elif isinstance(v, (list, tuple)):
                newDict[k] = handle_list(v)
            else:
                newDict[k] = copy.copy(v)
        return newDict

    def _to_json(self):
        """ Converts the O to JSON """
        return json.dumps(self._to_dict_recursive())

    def _pformat(self):
        """ Pretty Format the object """
        return pprint.pformat(self._to_dict_recursive())

    def _pp(self):
        """ Pretty Print the object """
        pprint.pprint(self._to_dict_recursive())

    def _update(self, newO):
        """ Update the current O with the fields from the given O """
        for x in newO:
            self[x] = newO[x]
        return self

    def _copy(self, **kwargs):
        """ Copies the object, adds kwargs to it, turning them into an O """
        data = self._to_dict_recursive()
        output = new_recursive(**data)
        new_data = new_recursive(**kwargs)
        return output._update(new_data)


def new_recursive(**data):
    """ Recursively converts all dicts to O and returns the object """
    newObj = O()
    def handle_list(l):
        out = []
        for x in l:
            if isinstance(x, dict):
                out.append(new_recursive(**x))
            elif isinstance(x, (list, tuple)):
                out.append(handle_list(x))
            else:
                out.append(x)
        return out

    for k, v in data.items():
        if isinstance(v, dict):
            newObj[k] = new_recursive(**v)
        elif isinstance(v, (list, tuple)):
            newObj[k] = handle_list(v)
        else:
            newObj[k] = v
    return newObj


def new_recursive_list(*data):
    """ Recursively converts all dicts in the given list of dicts to O and returns the list of new O objects """
    output = []
    for d in data:
        if isinstance(d, dict):
            output.append(new_recursive(**d))
        elif isinstance(d, (tuple, list)):
            output.append(new_recursive_list(*d))
        else:
            output.append(d)

    return output


class Folder(O):

    def _get_repr(self, level=0):
        if self.META:
            out = [self.META.name, "=" * len(self.META.name)]
        else:
            out = []

        for x in self:
            if x.startswith("_"):
                continue

            if isinstance(self[x], Folder):
                out.append(("--" * level) + self[x]._get_repr(level+1) + "\n")

        for x in self:
            if x.startswith("_"):
                continue

            if isinstance(self[x], Runner):
                out.append(("--" * (level+1)) + " " + self[x].short_repr() + "\n")

        return "\n".join(out)


    def __repr__(self):
        return self._get_repr()

class HistoryRunner(object):
    """
    Holds the state for a history request.
    Represents a ran request in the History that can be replayed.
    """
    def __init__(self, request, kwargs, env, middleware, auth, url, results=None, data=None, json=None):
        self.request = request
        self.kwargs = kwargs
        self.env = env
        self.middleware = middleware
        self.auth = auth
        self.url = url
        self.results = results
        self.data = data
        self.json = json

    def __repr__(self):
        return "[{method}] {url}".format(method=self.request["method"], url=self.url)

    def inner_run(self, kwargs):
        global J, D, R
        if kwargs is None:
            raise ValueError("Must pass kwargs to request from middleware")

        if self.auth is None:
            R = do_no_auth_request(self.request, self.url, **kwargs)
        elif isinstance(self.auth, requests.auth.AuthBase):
            R = do_custom_auth_request(self.request, self.url, self.auth, **kwargs)
        elif self.auth.type == "oAuth1":
            R = do_oauth1_request(self.request, self.url, self.auth, **kwargs)
        elif self.auth.type == "basicAuth":
            R = do_basic_auth_request(self.request, self.url, self.auth, **kwargs)
        elif self.auth.type == "digestAuth":
            R = do_digest_auth_request(self.request, self.url, self.auth, **kwargs)
        else:
            print("Attempting no auth request with unknown auth type", self.auth)
            R = do_no_auth_request(self.request, self.url, **kwargs)

        try:
            json_data = R.json()
            if isinstance(json_data, dict):
                J = new_recursive(**json_data)
            elif isinstance(json_data, (list, tuple)):
                J = new_recursive_list(*json_data)
            else:
                J = json_data
        except:
            pass

        D = R.content

        return R

    def __call__(self):
        """ Used to re-run from history """
        return self.middleware(self.inner_run, self.kwargs, self.env)


class Runner(object):
    """
    Holds the state for running a request.
    """
    def __init__(self, request, request_name, folder, env, middlewares):
        self.request = request
        self.request_name = request_name
        self.folder = folder
        self.env = env
        self.middlewares = middlewares
        self.META = O(**request)

    def default_data(self):
        data = get_default_request_data(self.request, env=self.env)
        try:
            return O(**json.loads(data))
        except:
            return data

    def add_env(self, **kwargs):
        return Runner(self.request,
                      self.request_name,
                      self.folder,
                      self.env._copy(**kwargs),
                      self.middlewares)

    def __repr__(self):
        return self.__doc__

    def short_repr(self):
        return "{name} - [{method}] {url}".format(name=self.request_name, method=self.request["method"], url=self.request["url"])

    def __call__(self, env=None, middlewares=None, auth=None, **kwargs):
        global R, H, J, D

        request = self.request
        request_name = self.request_name
        folder = self.folder
        env = env or self.env
        middlewares = middlewares or self.middlewares

        auth = auth or get_auth(request, env=env)

        kwargs = set_headers(request, kwargs, env=env)

        url, full_url, kwargs = set_url(request, kwargs, env=env)

        kwargs = set_body(request, kwargs, env=env)

        middleware = get_middleware(folder, request_name, middlewares=middlewares)

        runner = HistoryRunner(request, kwargs, env, middleware, auth, full_url)

        R = runner()
        runner.results = R
        runner.data = D
        runner.json = J
        H.history.append(runner)

        return R


class History(object):
    """Holds the history of the requests"""
    def __init__(self):
        self.history = []

    def __call__(self, run=None):
        """ Command to run or show history.  Run should be history index """
        if run is None:
            print(repr(self))
        else:
            return H.history[run]()

    def __repr__(self):
        return "\n".join(["{0}: {1}".format(idx, hist)
                          for idx, hist in enumerate(self.history)])

"""Holds the middleware"""
MW = O()
"""Holds last response's data, parsed to JSON as a O"""
J = None
"""Holds last response's data"""
D = None
"""Holds last response"""
R = None
"""Holds default loaded environment"""
E = O()
"""Holds default loaded collection"""
P = None
"""Holds call history"""
H = History()


def load_middleware(path):
    """ Load the middleware python script """
    middlewares = O()
    loader = importlib.machinery.SourceFileLoader('middleware', path)
    middleware = loader.load_module()
    for mw in (d for d in dir(middleware) if not d.startswith("__")):
        middlewares[mw] = getattr(middleware, mw)
    return middlewares


def load_collection(path, merge=None):
    """ Load the collection file at the given path, and return the requests"""
    if isinstance(path, str):
        path = open(path)
    coll = json.load(path)
    path.close()
    parsed = parse_requests(coll)
    if merge is None:
        return parsed
    else:
        for i in parsed:
            merge[i] = parsed[i]
        return merge


def load_environment(path, merge=None):
    """ Load the environment file at the given path, and return the env data"""
    if isinstance(path, str):
        path = open(path)
    env_data = json.load(path)
    path.close()
    merge = merge or O()
    for item in env_data["values"]:
        merge[item["key"]] = item["value"]
    return merge


def parse_args():
    """ Parse command line args """
    parser = argparse.ArgumentParser(description='Postman Repl')

    parser.add_argument('collection_path', type=open, metavar='Collection',
                    help='The path to the postman collection file')

    parser.add_argument('--env', '-e', dest='env_path', type=open,
                    help='The path to a Postman environment file')

    parser.add_argument('--middleware', '-m', dest='middleware_path',
                    help='The path to a middleware file')

    args = parser.parse_args()

    if not args.collection_path:
        print("Must suppy a collection path")
        sys.exit(1)

    return args


def env_replace(data, env):
    """Template the text data with the environment data"""
    return Template(data).render(**env._to_dict())

def set_headers(request, kwargs, env=None):
    """ Set the request headers onto the kwargs for the request """
    env = env or E
    headers = {}
    splits = request["headers"].split("\n")
    for split in splits:
        if not split:
            continue
        name, _, val = split.partition(":")
        headers[name.strip()] = env_replace(val.strip(), env)

    if 'headers' in kwargs:
        headers.update(kwargs["headers"])

    kwargs["headers"] = headers
    return kwargs


def set_url(request, kwargs, env=None):
    """ Set the URL string for the request, additionally setting params into kwargs for request """
    env = env or E
    url = env_replace(request["url"], env)
    parsed_url = urlparse(url)
    url, _, _ = parsed_url.geturl().partition('?')
    params = parse_qs(parsed_url.query)

    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            # TODO: Support parameter arrays?
            v = v[0]

        if v:
            params[k] = env_replace(v, env)
        else:
            params[k] = ""

    if params and kwargs.get("params"):
        params.update(kwargs["params"])

    kwargs["params"] = params

    if kwargs["params"]:
        full_url = url + '?'
        for k, v in kwargs["params"].items():
            full_url = full_url + "&" + k + "=" + v
    else:
        full_url = url

    return url, full_url, kwargs


def get_default_request_data(request, env=None):
    """ Get the default request data from the request, given the env """
    env = env or E
    if request.get("rawModeData"):
        return env_replace(request["rawModeData"], env)
    elif request.get("data"):
        raise NotImplementedError("Not yet handing data format, only raw data")


def set_body(request, kwargs, env=None):
    """ Sets the body data on the request kwargs """
    env = env or E
    if not 'data' in kwargs and not 'json' in kwargs:
        kwargs["data"] = get_default_request_data(request, env=env)
    elif 'data' in kwargs and isinstance(kwargs['data'], O):
        kwargs["data"] = kwargs["data"]._to_dict()
    elif 'json' in kwargs and isinstance(kwargs['json'], O):
        kwargs["json"] = kwargs["json"]._to_dict()
    return kwargs


def get_middleware(folder, request_name, middlewares=None):
    """ Gets the middleware for the given folder + request """
    middlewares = middlewares or MW
    if folder:
        middleware = middlewares[folder.META.folder_name + "_" + request_name]
    else:
        middleware = middlewares[request_name]

    if middleware is None:
        def default_middleware(run, kwargs, env):
            return run(kwargs)
        middleware = default_middleware

    return middleware


def make_docstring(request, folder, method):
    """ Makes a docstring for the given request method """
    if folder:
        docstring = folder.META.folder_name.title() + " / " + request["name"] + ":\n"

    else:
        docstring = request["name"] + ":\n"

    docstring += "[{method}] {url}\n".format(method=request["method"],
                                             url=request["url"])

    if request["description"]:
        docstring += request["description"]
    if request["headers"]:
        docstring += "\nDefault Headers:\n{headers}".format(headers=request["headers"])
    if request["dataMode"] == "raw" and request["rawModeData"]:
        docstring += "\nDefault Data:\n{data}".format(data=request["rawModeData"])
    auth = get_auth(request)
    if auth:
        docstring += "\nDefault Auth Data:\n{auth}".format(auth=auth._pformat())

    method.__doc__ = docstring
    return method


def do_no_auth_request(request, url, **kwargs):
    """Makes a normal request"""
    print("Making Request: ")
    print("METHOD: ", request["method"])
    print("URL: ", url)
    print("Params: ", json.dumps(kwargs.get("params")))
    print("Headers: ", json.dumps(kwargs.get("headers")))
    print("Data: \n", kwargs.get("data"))

    return requests.request(request["method"], url, **kwargs)


def do_custom_auth_request(request, url, auth_data, **kwargs):
    """Makes a normal request"""
    print("Making Request: ")
    print("METHOD: ", request["method"])
    print("URL: ", url)
    print("Params: ", json.dumps(kwargs.get("params")))
    print("Headers: ", json.dumps(kwargs.get("headers")))
    print("Custom Auth Data: ", auth_data)
    print("Data: \n", kwargs.get("data"))

    return requests.request(request["method"], url, **kwargs)


def do_basic_auth_request(request, url, auth_data, **kwargs):
    """Makes a normal request"""
    from requests.auth import HTTPBasicAuth
    auth = HTTPBasicAuth(auth_data.username, auth_data.password)

    print("Making Request: ")
    print("METHOD: ", request["method"])
    print("URL: ", url)
    print("Params: ", json.dumps(kwargs.get("params")))
    print("Headers: ", json.dumps(kwargs.get("headers")))
    print("Basic Auth Data: ", auth_data)
    print("Data: \n", kwargs.get("data"))

    return requests.request(request["method"], url, auth=auth, **kwargs)


def do_digest_auth_request(request, url, auth_data, **kwargs):
    """Makes a normal request"""
    from requests.auth import HTTPDigestAuth
    auth = HTTPDigestAuth(auth_data.username, auth_data.password)

    print("Making Request: ")
    print("METHOD: ", request["method"])
    print("URL: ", url)
    print("Params: ", json.dumps(kwargs.get("params")))
    print("Headers: ", json.dumps(kwargs.get("headers")))
    print("Digest Auth Data: ", auth_data)
    print("Data: \n", kwargs.get("data"))

    return requests.request(request["method"], url, auth=auth, **kwargs)


def do_oauth1_request(request, url, auth_data, **kwargs):
    """Makes a normal request"""
    from requests_oauthlib import OAuth1

    auth = OAuth1(auth_data.consumer_key,
                  auth_data.consumer_secret,
                  auth_data.access_token,
                  auth_data.access_token_secret,
                  signature_type='auth_header')


    print("Making oAuth1 Request: ")
    print("METHOD: ", request["method"])
    print("URL: ", url)
    print("Params: ", json.dumps(kwargs.get("params")))
    print("Headers: ", json.dumps(kwargs.get("headers")))
    print("OAuth1 Data: ", auth_data)
    print("Data: \n", kwargs.get("data"))

    return requests.request(request["method"],
                            url,
                            auth=auth,
                            **kwargs)


def get_auth(request, env=None):
    """Get the auth information for the request"""
    env = env or E
    auth = request.get('currentHelper', None)
    auth_data = request.get('helperAttributes', {})
    if auth == "oAuth1":
        return O(type=auth,
                 consumer_key=env_replace(auth_data['consumerKey'], env),
                 consumer_secret=env_replace(auth_data['consumerSecret'], env),
                 access_token=env_replace(auth_data['token'], env),
                 access_token_secret=env_replace(auth_data['tokenSecret'], env))
    elif auth == "basicAuth":
        return O(type=auth,
                 username=env_replace(auth_data['username'], env),
                 password=env_replace(auth_data['password'], env))
    elif auth == "digestAuth":
        return O(type=auth,
                 username=env_replace(auth_data['username'], env),
                 password=env_replace(auth_data['password'], env))
    elif auth is None or auth == "normal":
        return None
    else:
        print("UNKNOWN AUTH TYPE: ", auth)
        return None


def make_request(request, request_name, folder):
    """ Create a request that can be called from the repl """
    do_request = Runner(request, request_name, folder, E, MW)

    do_request.__name__ = request_name
    do_request = make_docstring(request, folder, do_request)

    return do_request


def get_request_folder(request, folders):
    """ Gets the folder the request belongs to """
    for key in folders:
        folder = folders[key]
        if folder.META and folder.META.order and request["id"] in folder.META.order:
            return folder


def fix_name(name):
    """ Fix the names so that they are valid python variable names """
    name = name.lower()
    name = re.sub(r'[^a-z0-9_]+', '_', name).strip('_')
    name = re.sub(r'[_]+', '_', name)
    name = re.sub(r'^[0-9_]+', '', name)

    return name


def parse_requests(coll):
    """ Parse out the requests and folders from the collection file """
    folders = Folder()
    if "folders" in coll:
        for folder in coll["folders"]:
            folder_name = fix_name(folder["name"])
            folders[folder_name] = Folder(META=O(folder_name=folder_name, **folder))

    for request in coll["requests"]:
        folder = get_request_folder(request, folders)
        request_name = fix_name(request["name"])
        if folder:
            folder[request_name] = make_request(request, request_name, folder)
        else:
            folders[request_name] = make_request(request, request_name, None)

    return folders


def main():
    """ Main entry point for repl """
    global E, P, MW

    args = parse_args()
    if args.env_path:
        E = load_environment(args.env_path)
    P = load_collection(args.collection_path)
    if args.middleware_path:
        MW = load_middleware(args.middleware_path)
    IPython.embed()


if __name__ == "__main__":
    main()

