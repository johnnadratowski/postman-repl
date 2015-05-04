#!/usr/bin/python
"""
Tests for postman repl
"""

import unittest
import urllib
import postman_repl as pmr
import json


class TestO(unittest.TestCase):

    def test_init(self):
        test = pmr.O(x=1, y=2)
        self.assertDictEqual(test.__dict__, {'x': 1, 'y': 2})

    def test_get(self):
        test = pmr.O(x=1, y=2)
        self.assertEqual(test["x"], 1)
        self.assertEqual(test.x, 1)

    def test_set(self):
        test = pmr.O(x=1, y=2)
        test.x = 2
        self.assertEqual(test["x"], 2)
        self.assertEqual(test.x, 2)

    def test_del(self):
        test = pmr.O(x=1, y=2)
        del test.x
        self.assertEqual(test.x, None)
        self.assertDictEqual(test.__dict__, {'y': 2})

    def test_iter(self):
        test = pmr.O(x=1, y=2)
        for k in test:
            self.assertTrue(k == "x" or k == "y")
            self.assertTrue(test[k] == 1 or test[k] == 2)

    def test_todict(self):
        test = pmr.O(x=1, y=2)
        self.assertDictEqual(test.__dict__, {'x': 1, 'y': 2})

    def test_todict_recursive(self):
        test = pmr.O(x=1, y=2, z=pmr.O(x=1, y=2))
        self.assertDictEqual(test._to_dict_recursive(),
                             {'x': 1, 'y': 2, 'z': {'x': 1, 'y': 2}})

    def test_tojson(self):
        test = pmr.O(x=1, y=2, z=pmr.O(x=1, y=2))
        self.assertDictEqual(json.loads(test._to_json()),
                             {'x': 1, 'y': 2, 'z': {'x': 1, 'y': 2}})

    def test_new_recursive(self):
        expect = pmr.O(x=1, y=2, z=pmr.O(x=1, y=2))
        test = {'x': 1, 'y': 2, 'z': {'x': 1, 'y': 2}}
        test = pmr.new_recursive(**test)
        self.assertEqual(test._to_dict_recursive(), expect._to_dict_recursive())

    def test_new_recursive_list(self):
        expect = [
            {'x': 1, 'y': 2, 'z': {'x': 1, 'y': 2}},
            {'x': 1, 'y': 2, 'z': {'x': 1, 'y': 2}}]
        test = [
            pmr.O(
                x=1, y=2, z=pmr.O(
                    x=1, y=2)), pmr.O(
                x=1, y=2, z=pmr.O(
                    x=1, y=2))]
        test = pmr.new_recursive_list(*test)
        self.assertListEqual([x._to_dict_recursive() for x in test], expect)


class TestPostmanRepl(unittest.TestCase):

    def setUp(self):
        self.coll_file = "../examples/JIRA.json.postman_collection"
        self.env_file = "../examples/test.env"
        self.mw_file = "../examples/middleware.py"

        self.collection = pmr.load_collection(self.coll_file)
        self.env = pmr.load_environment(self.env_file)
        self.mw = pmr.load_middleware(self.mw_file)

    def tearDown(self):
        pmr.H.history = []
        pmr.R = None
        pmr.J = None
        pmr.D = None
        pmr.MW = pmr.O()
        pmr.E = pmr.O()
        pmr.P = None

    def test_load_collection(self):

        self.assertTrue("sprints" in self.collection)
        self.assertTrue("META" in self.collection["sprints"])
        self.assertTrue("rapidview" in self.collection["sprints"])
        self.assertTrue("sprint" in self.collection["sprints"])
        self.assertTrue("sprint_issues" in self.collection["sprints"])

        self.assertTrue("users" in self.collection)
        self.assertTrue("META" in self.collection["users"])
        self.assertTrue("search_username" in self.collection["users"])

    def test_load_environment(self):

        self.assertDictEqual(self.env._to_dict_recursive(), {
            "host": "localhost",
            "protocol": "http",
            "port": "8081",
            "username": "user",
            "password": "password",
        })

    def test_middleware(self):
        called = [False]
        def middleware(run, kwargs, env):
            called[0] = True

        middlewares = pmr.O(sprints_sprint=middleware)
        self.collection["sprints"]["sprint"](env=self.env, middlewares=middlewares)
        self.assertTrue(called[0])

    def test_get_default_data(self):
        expect = {'password': '', 'username': ''}
        test = self.collection["sprints"]["sprint"].default_data().__dict__
        self.assertDictEqual(expect, test)

    def test_call(self):
        called = [False, False, False]
        i = [0]
        def middleware(run, kwargs, env):
            called[i[0]] = True
            i[0] += 1

        middlewares = pmr.O(sprints_sprint=middleware,
                            sprints_sprint_issues=middleware,
                            sprints_rapidview=middleware)
        self.collection["sprints"]["sprint"](params={'includeHistoricSprints': 'false'}, env=self.env, middlewares=middlewares)
        self.collection["sprints"]["sprint_issues"](env=self.env, middlewares=middlewares)
        self.collection["sprints"]["rapidview"](env=self.env, middlewares=middlewares)
        self.assertTrue(all(called))

        url = urllib.parse.urlparse(pmr.H.history[0].url)
        self.assertEqual(url.path, "/rest/greenhopper/latest/sprintquery/")
        self.assertDictEqual(urllib.parse.parse_qs(url.query), {'includeHistoricSprints': ['false'], 'includeFutureSprints': ['true']})

        self.assertEqual(pmr.H.history[1].url, "https://unified.jira.com/rest/greenhopper/latest/rapid/charts/sprintreport")

        self.assertEqual(pmr.H.history[2].url, "https://unified.jira.com/rest/greenhopper/latest/rapidviews/list")

    def test_history(self):
        called = [False, False, False, False]
        i = [0]
        def middleware(run, kwargs, env):
            called[i[0]] = True
            i[0] += 1

        middlewares = pmr.O(sprints_sprint=middleware,
                            sprints_sprint_issues=middleware,
                            sprints_rapidview=middleware)
        self.collection["sprints"]["sprint"](env=self.env, middlewares=middlewares)
        self.collection["sprints"]["sprint_issues"](env=self.env, middlewares=middlewares)
        self.collection["sprints"]["rapidview"](env=self.env, middlewares=middlewares)

        self.assertEqual(len(pmr.H.history), 3)
        pmr.H(0)
        self.assertTrue(all(called))

    def test_help(self):
        expect = """Sprints / Sprint:
GET https://unified.jira.com/rest/greenhopper/latest/sprintquery/{{rapidViewId}}?includeHistoricSprints=true&includeFutureSprints=true
Get a specific sprint from Jira

Default Headers:
Authorization: Basic am9objphbkdlbDgz


Default Data:
{
  "username": "{{username}}",
  "password": "{{password}}"
}"""
        self.assertEqual(expect, self.collection["sprints"]["sprint"].__doc__)

if __name__ == '__main__':
    unittest.main()
