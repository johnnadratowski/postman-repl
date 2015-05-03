def authentication_authenticate(run, kwargs, env):
    result = run(kwargs)
    try:
        env.token = result.json()["token"]
    except:
        print("Couldnt set token!")
    return result
