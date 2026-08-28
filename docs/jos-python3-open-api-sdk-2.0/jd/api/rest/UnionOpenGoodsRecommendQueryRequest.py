from jd.api.base import RestApi

class UnionOpenGoodsRecommendQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.RecommendGoodsReq = None

		def getapiname(self):
			return 'jd.union.open.goods.recommend.query'

		def get_version(self):
			return '1.0'
			
	

class RecommendGoodsReq(object):
		def __init__(self):
			"""
			"""
			self.itemId = None
			self.sceneId = None
			self.keyword = None
			self.skuId = None





