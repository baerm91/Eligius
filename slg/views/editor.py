"""Authenticated object editing and modal forms."""

from bootstrap_modal_forms.generic import BSModalCreateView, BSModalUpdateView
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.forms import inlineformset_factory
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy

from ..forms import DetailUpdateForm, ObjForm, StaffDetailUpdateForm
from ..models import AvBildtyp, Obj, Obj_Person, Obj_Ref, RvBildtyp
from ..permissions import is_active_staff


class StaffModelPermissionMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Nur aktive Staff-Accounts mit den angegebenen Model-Permissions."""

    required_permissions = ()
    raise_exception = False

    def test_func(self):
        user = self.request.user
        return is_active_staff(user) and user.has_perms(self.required_permissions)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            self.raise_exception = True
        return super().handle_no_permission()


class ObjCreateView(StaffModelPermissionMixin, BSModalCreateView):
    required_permissions = ('slg.add_obj',)
    template_name = 'slg/create_object.html'
    form_class = ObjForm
    success_message = 'Success: Objekt was created.'
    success_url = reverse_lazy('Objektliste')

# Update

class ObjUpdateView(StaffModelPermissionMixin, BSModalUpdateView):
    required_permissions = ('slg.change_obj',)
    model = Obj
    template_name = 'slg/update_obj.html'
    form_class = ObjForm
    success_message = 'Success: Obj was updated.'
    success_url = reverse_lazy('Objektliste')

@staff_member_required
@permission_required('slg.change_obj', raise_exception=True)
def MzUpdate(request, id):
   obj = get_object_or_404(Obj, id=id)
   # Verwaltungsfelder nur für Superuser (wie ObjDetailUpdateSerializer).
   DetailForm = DetailUpdateForm if request.user.is_superuser else StaffDetailUpdateForm
   PersonFormSet = inlineformset_factory(Obj, Obj_Person, fields=('idfk_Person','idfk_PersonFunktion','appears_on_rev'), can_delete=True, extra=2)
   RefFormSet = inlineformset_factory(Obj, Obj_Ref, fields=('idfk_Ref','nummer', 'nach', 'variante', 'link'), can_delete=True, extra=1,)
   # RefFormSet = inlineformset_factory(Obj, Obj_Ref, form=RefUpdateForm, can_delete=True, extra=1,)
   #print(formset)
   form = DetailForm(instance=obj)
   if request.method == 'POST':
      #print("erstes IF")
      #print(request.POST)
      Personen = PersonFormSet(request.POST, instance=obj, prefix='personen')
      Literatur = RefFormSet(request.POST, instance=obj, prefix='referenzen')
      form = DetailForm(request.POST, instance=obj)
      if form.is_valid() and Literatur.is_valid() and Personen.is_valid():
         with transaction.atomic():
            form.save()
            Literatur.save()
            Personen.save()
         # Personen = Personen.save(commit=False)
         # for inline_form in Personen:
         #        #if inline_form.cleaned_data:
         #            #person = inline_form.save(commit=False)
         #            inline_form.save()
         #formset.save()
         # Literatur = Literatur.save(commit=False)
         # for inline_form in Literatur:
         #        #if inline_form.cleaned_data:
         #            #person = inline_form.save(commit=False)
         #            inline_form.save()
         #formset.save()
         return HttpResponseRedirect(request.path_info)
   else:
      Personen = PersonFormSet(instance=obj, prefix='personen')
      Literatur = RefFormSet(instance=obj, prefix='referenzen')
   avtype = AvBildtyp.objects.all().order_by('name')
   rvtype = RvBildtyp.objects.all().order_by('name')




   context = {
      'form': form,
      'Personen': Personen,
      'Refs': Literatur,
      'test': obj,
      'Avtypes': avtype,
      'Rvtypes': rvtype,

   }


      # if form.is_valid():
      #    form.save()
         #return redirect('/')
   # def form_valid(self, form):
   #    print(form.cleaned_data)
   #    return super().form_valid(form)

   # def get_object(self):
   #    id_ = self.kwargs.get("id")
   #    return get_object_or_404(Obj, id=id_)

   return render(request, 'slg/obj_form.html', context)
