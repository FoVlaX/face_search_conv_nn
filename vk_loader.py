import vk_api
import requests

def load_photos_from_vk(offset, count, callback):
    vk_session = vk_api.VkApi('+79523783991', '8io98IO9')
    vk_session.auth(reauth=True)
    vk = vk_session.get_api()
    data = vk.users.search(sort = 0,group = 91050183, offset = offset, count = count, age_from = 18, age_to = 25, status = 6, country = 1, city = 105,fields = 'photo_max_orig', online = 0) #sex = 1
    for i in range(count):
        try:
            s = 'vk.com/id'+str(data['items'][i]['id'])
            p = requests.get(data['items'][i]['photo_max_orig'])
            callback(s, p.content)
        except:
            print(i)
            break
