import re

class ConnMatrix(object):

    def __init__(self):
        self.matches = {}

    def add(self, node, match, rate):
        self.matches[node] = (match, rate)

    def links(self, node):
        if node not in self.matches.keys():
            return

        return self.matches[node]

        # match = self.matches[node]
        # for n in self.matches.keys():
        #     if node == n:
        #         continue
        #     else:
        #         if re.match(match, n):
        #             yield n
