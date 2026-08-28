from jd.api.base import RestApi

class UnionOpenCpPromotionGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpPromotionInfoReq = None

		def getapiname(self):
			return 'jd.union.open.cp.promotion.get'

		def get_version(self):
			return '1.0'
			
	

class CpPromotionInfoReq(object):
		def __init__(self):
			"""
			"""
			self.proType = None
			self.giftCouponKey = None
			self.couponUrl = None
			self.pid = None
			self.weChatType = None
			self.chainType = None
			self.rid = None
			self.command = None
			self.subUnionId = None
			self.activityId = None
			self.itemId = None
			self.positionId = None
			self.channelId = None





