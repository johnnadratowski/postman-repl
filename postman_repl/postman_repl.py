#!/usr/bin/python
"""
Script for starting a repl with postman configs/env loaded.
"""


import argparse
import importlib.machinery
import IPython
from jinja2 import Template
import json
import pprint
import re
import requests
import sys
from urllib.parse import urlparse, parse_qs


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
                    out.append(x)
            return out

        newDict = {}
        for k, v in self.__dict__.items():
            if isinstance(v, O):
                newDict[k] = v._to_dict_recursive()
            elif isinstance(v, (list, tuple)):
                newDict[k] = handle_list(v)
            else:
                newDict[k] = v
        return newDict

    def _to_json(self):
        """ Converts the O to JSON """
        return json.dumps(self._to_dict_recursive())

    def _pp(self):
        """ Pretty Print the object """
        pprint.pprint(self._to_dict_recursive())


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


def history(run=None):
    """ Command to run or show history.  Run should be history index """
    global H
    if run is None:
        for idx, hist in enumerate(H.history):
            print("{0}: {1}".format(idx, hist.url))
    else:
        return H.history[run]()


"""Holds call history"""
H = history
H.history = []


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


def set_headers(request, kwargs, env=None):
    """ Set the request headers onto the kwargs for the request """
    env = env or E
    headers = {}
    splits = request["headers"].split("\n")
    for split in splits:
        if not split:
            continue
        name, _, val = split.partition(":")
        headers[name.strip()] = Template(val.strip()).render(**env._to_dict())

    if 'headers' in kwargs:
        headers.update(kwargs["headers"])

    kwargs["headers"] = headers
    return kwargs


def set_url(request, kwargs, env=None):
    """ Set the URL string for the request, additionally setting params into kwargs for request """
    env = env or E
    url = Template(request["url"]).render(**env._to_dict())
    parsed_url = urlparse(url)
    url, _, _ = parsed_url.geturl().partition('?')
    params = parse_qs(parsed_url.query)

    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            # TODO: Support parameter arrays?
            v = v[0]

        if v:
            params[k] = Template(v).render(**env._to_dict())
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
        return Template(request["rawModeData"]).render(**env._to_dict())
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
    docstring += request["method"] + " " + request["url"] + "\n"
    if request["description"]:
        docstring += request["description"]
    if request["headers"]:
        docstring += "\n\nDefault Headers:\n"
        docstring += request["headers"]
    if request["dataMode"] == "raw" and request["rawModeData"]:
        docstring += "\n\nDefault Data:\n"
        docstring += request["rawModeData"]
    method.__doc__ = docstring
    return method


def make_request(request, request_name, folder):
    """ Create a request that can be called from teh repl """
    def do_request(env=None, middlewares=None, **kwargs):
        """ Run the request, setting the global variables for the response """
        global R, H, J, D
        env = env or E
        middlewares = middlewares or MW
        kwargs = set_headers(request, kwargs, env=env)

        url, full_url, kwargs = set_url(request, kwargs, env=env)

        kwargs = set_body(request, kwargs, env=env)

        middleware = get_middleware(folder, request_name, middlewares=middlewares)

        def inner_run(kwargs):
            global J, D, R, H
            if kwargs is None:
                raise ValueError("Must pass kwargs to request from middleware")

            print("Making Request: ")
            print("METHOD: ", request["method"])
            print("URL: ", url)
            print("Params: ", json.dumps(kwargs.get("params")))
            print("Headers: ", json.dumps(kwargs.get("headers")))
            print("Data: \n", kwargs.get("data"))

            R = requests.request(request["method"], url, **kwargs)

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

        def history_run():
            """ Used to re-run from history """
            return middleware(inner_run, kwargs, env)

        R = history_run()
        setattr(history_run, 'results', R)
        setattr(history_run, 'data', D)
        setattr(history_run, 'json', J)
        setattr(history_run, 'url', full_url)
        H.history.append(history_run)

        return R

    setattr(do_request, 'META', O(**request))

    def get_data(env=None):
        env = env or E
        data = get_default_request_data(request, env=env)
        try:
            return O(**json.loads(data))
        except:
            return data
    setattr(do_request, 'default_data', get_data)

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
    folders = O()
    if "folders" in coll:
        for folder in coll["folders"]:
            folder_name = fix_name(folder["name"])
            folders[folder_name] = O(META=O(folder_name=folder_name, **folder))

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

