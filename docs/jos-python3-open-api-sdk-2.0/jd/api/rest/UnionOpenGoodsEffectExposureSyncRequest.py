from jd.api.base import RestApi

class UnionOpenGoodsEffectExposureSyncRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.syncExposureReq = None

		def getapiname(self):
			return 'jd.union.open.goods.effect.exposure.sync'

		def get_version(self):
			return '1.0'
			
	

class ExposureInfo(object):
		def __init__(self):
			"""
			"""
			self.itemId = None
			self.extMap = None
			self.pos = None
			self.id = None
			self.timestamp = None


class SyncExposureReq(object):
		def __init__(self):
			"""
			"""
			self.exposureInfoList = None





