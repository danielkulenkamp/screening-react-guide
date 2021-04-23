class Observer(object):

    def __init__(self, observation_fn, dev):
        self.dev = dev
        self.observation_fn = observation_fn

        self.new_survey = self.observation_fn(self.dev)
        self.old_survey = {}

    def update(self):
        self.old_survey = self.new_survey
        self.new_survey = self.observation_fn(self.dev)

    def surveysays(self, question):
        return self.new_survey[question] - self.old_survey[question]
