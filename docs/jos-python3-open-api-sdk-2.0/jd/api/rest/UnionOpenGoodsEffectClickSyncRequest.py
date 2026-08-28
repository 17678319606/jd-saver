from jd.api.base import RestApi

class UnionOpenGoodsEffectClickSyncRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.syncClickReq = None

		def getapiname(self):
			return 'jd.union.open.goods.effect.click.sync'

		def get_version(self):
			return '1.0'
			
	

class ClickInfo(object):
		def __init__(self):
			"""
			"""
			self.itemId = None
			self.extMap = None
			self.pos = None
			self.id = None
			self.timestamp = None


class SyncClickReq(object):
		def __init__(self):
			"""
			"""
			self.clickInfoList = None





