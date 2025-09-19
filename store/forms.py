from django import forms


class CheckoutForm(forms.Form):
    full_name = forms.CharField(label='Имя и фамилия', max_length=150)
    email = forms.EmailField(label='Email')
    company = forms.CharField(label='Компания', max_length=150, required=False)
    notes = forms.CharField(
        label='Комментарий',
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()
