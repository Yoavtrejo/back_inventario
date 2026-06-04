from rest_framework import serializers
from .models import LoanHistory

class LoanHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanHistory
        fields = '__all__'
