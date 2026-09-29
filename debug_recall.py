import os
from hindsight_client import Hindsight

c = Hindsight(base_url=os.environ["HINDSIGHT_URL"], api_key=os.environ["HINDSIGHT_API_KEY"])
bank = os.environ["HINDSIGHT_BANK"]
print("bank:", bank)
r = c.recall(bank_id=bank, query="payment retry config change on payments service")
print(r)