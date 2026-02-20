"""
Printer Management Views
"""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import PrinterConfiguration, PrintJob, PrinterTaskMapping
from .forms import PrinterConfigurationForm, PrinterTaskMappingForm
from .printing import PrinterManager
import logging

logger = logging.getLogger(__name__)

# Maps the 3 top-level roles to specific task_name keys in PrinterTaskMapping
PRINTER_ROLES = {
    'receipt': 'receipt_pos',
    'barcode': 'barcode_label',
    'report':  'sales_report',
}


@login_required(login_url='login')
def printer_management(request):
    """Main printer management page"""
    printers = PrinterConfiguration.objects.all()
    recent_jobs = PrintJob.objects.select_related('printer', 'created_by')[:20]

    # Get system printers and build availability set
    system_printers = PrinterManager.get_system_printers()
    system_printer_names = {p['name'] for p in system_printers}

    # Annotate each configured printer with live availability
    for p in printers:
        p.is_available = p.system_printer_name in system_printer_names

    # Build role assignment context
    role_assignments = {}
    for role, task_name in PRINTER_ROLES.items():
        mapping = (
            PrinterTaskMapping.objects
            .filter(task_name=task_name)
            .select_related('printer')
            .first()
        )
        assigned_printer = mapping.printer if mapping else None
        role_assignments[role] = {
            'mapping':   mapping,
            'printer':   assigned_printer,
            'available': (
                assigned_printer is not None
                and assigned_printer.system_printer_name in system_printer_names
            ),
        }

    active_printers = PrinterConfiguration.objects.filter(is_active=True)

    context = {
        'printers':         printers,
        'active_printers':  active_printers,
        'recent_jobs':      recent_jobs,
        'system_printers':  system_printers,
        'role_assignments': role_assignments,
    }
    return render(request, 'printer/printer_management.html', context)


@login_required(login_url='login')
@csrf_exempt
def save_printer_roles(request):
    """AJAX POST — save a single role → printer assignment."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)

    if not request.user.has_perm('store.change_printertaskmapping') and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    role = data.get('role')
    printer_id = data.get('printer_id')  # int or None

    task_name = PRINTER_ROLES.get(role)
    if not task_name:
        return JsonResponse({'success': False, 'message': f'Unknown role: {role}'}, status=400)

    printer = None
    if printer_id:
        printer = get_object_or_404(PrinterConfiguration, pk=printer_id, is_active=True)

    mapping, created = PrinterTaskMapping.objects.get_or_create(
        task_name=task_name,
        defaults={'printer': printer, 'is_active': True},
    )
    if not created:
        mapping.printer = printer
        mapping.is_active = True
        mapping.save(update_fields=['printer', 'is_active', 'updated_at'])

    return JsonResponse({
        'success':      True,
        'created':      created,
        'role':         role,
        'printer_name': printer.name if printer else None,
        'printer_system_name': printer.system_printer_name if printer else None,
        'message': (
            f"{'Assigned' if printer else 'Cleared'} {role} printer"
            + (f" → {printer.name}" if printer else "")
        ),
    })


@login_required(login_url='login')
def add_printer(request):
    """Add a new printer configuration"""
    if request.method == 'POST':
        form = PrinterConfigurationForm(request.POST)
        if form.is_valid():
            printer = form.save(commit=False)
            printer.created_by = request.user
            printer.save()
            messages.success(request, f"Printer '{printer.name}' added successfully!")
            return redirect('printer_management')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PrinterConfigurationForm()

    return render(request, 'printer/add_printer.html', {'form': form})


@login_required(login_url='login')
def edit_printer(request, pk):
    """Edit printer configuration"""
    printer = get_object_or_404(PrinterConfiguration, pk=pk)

    if request.method == 'POST':
        form = PrinterConfigurationForm(request.POST, instance=printer)
        if form.is_valid():
            form.save()
            messages.success(request, f"Printer '{printer.name}' updated successfully!")
            return redirect('printer_management')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PrinterConfigurationForm(instance=printer)

    return render(request, 'printer/edit_printer.html', {'form': form, 'printer': printer})


@login_required(login_url='login')
def delete_printer(request, pk):
    """Delete printer configuration"""
    printer = get_object_or_404(PrinterConfiguration, pk=pk)

    if request.method == 'POST':
        printer_name = printer.name
        printer.delete()
        messages.success(request, f"Printer '{printer_name}' deleted successfully!")
        return redirect('printer_management')

    return render(request, 'printer/delete_printer.html', {'printer': printer})


@login_required(login_url='login')
def test_printer(request, pk):
    """Test printer by printing a test page"""
    printer = get_object_or_404(PrinterConfiguration, pk=pk)

    try:
        success = PrinterManager.test_printer(printer)

        if success:
            messages.success(request, f"Test page sent to '{printer.name}' successfully!")
        else:
            messages.error(request, f"Failed to print test page to '{printer.name}'")

    except Exception as e:
        logger.error(f"Test print error: {str(e)}")
        messages.error(request, f"Error: {str(e)}")

    return redirect('printer_management')


@login_required(login_url='login')
def set_default_printer(request, pk):
    """Set a printer as the default for its type"""
    printer = get_object_or_404(PrinterConfiguration, pk=pk)

    # Unset other defaults of same type
    PrinterConfiguration.objects.filter(
        printer_type=printer.printer_type,
        is_default=True
    ).update(is_default=False)

    # Set this one as default
    printer.is_default = True
    printer.save()

    messages.success(request, f"'{printer.name}' set as default {printer.get_printer_type_display()}")
    return redirect('printer_management')


@login_required(login_url='login')
def toggle_printer_status(request, pk):
    """Toggle printer active/inactive status"""
    printer = get_object_or_404(PrinterConfiguration, pk=pk)

    printer.is_active = not printer.is_active
    printer.save()

    status = "activated" if printer.is_active else "deactivated"
    messages.success(request, f"Printer '{printer.name}' {status}")

    return redirect('printer_management')


@login_required(login_url='login')
def print_job_history(request):
    """View print job history"""
    jobs = PrintJob.objects.select_related('printer', 'created_by').all()

    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        jobs = jobs.filter(status=status_filter)

    # Filter by printer type if provided
    printer_type = request.GET.get('printer_type')
    if printer_type:
        jobs = jobs.filter(printer__printer_type=printer_type)

    context = {
        'jobs': jobs[:100],  # Limit to recent 100 jobs
        'status_filter': status_filter,
        'printer_type': printer_type,
    }

    return render(request, 'printer/print_job_history.html', context)


@login_required(login_url='login')
def get_system_printers_ajax(request):
    """AJAX endpoint to get system printers"""
    try:
        printers = PrinterManager.get_system_printers()
        return JsonResponse({
            'success': True,
            'printers': printers
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required(login_url='login')
def task_printer_mapping(request):
    """Manage task to printer mappings"""
    mappings = PrinterTaskMapping.objects.select_related('printer').all()
    printers = PrinterConfiguration.objects.filter(is_active=True)

    # Get all possible tasks
    all_tasks = PrinterTaskMapping.TASK_CHOICES

    # Find tasks that don't have mappings yet
    existing_tasks = set(mappings.values_list('task_name', flat=True))
    available_tasks = [task for task in all_tasks if task[0] not in existing_tasks]

    context = {
        'mappings': mappings,
        'printers': printers,
        'available_tasks': available_tasks,
    }
    return render(request, 'printer/task_mapping.html', context)


@login_required(login_url='login')
def add_task_mapping(request):
    """Add a new task mapping"""
    if request.method == 'POST':
        form = PrinterTaskMappingForm(request.POST)
        if form.is_valid():
            mapping = form.save()
            messages.success(request, f"Task mapping '{mapping.get_task_name_display()}' created successfully!")
            return redirect('task_printer_mapping')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PrinterTaskMappingForm()

    return render(request, 'printer/add_task_mapping.html', {'form': form})


@login_required(login_url='login')
def edit_task_mapping(request, pk):
    """Edit an existing task mapping"""
    mapping = get_object_or_404(PrinterTaskMapping, pk=pk)

    if request.method == 'POST':
        form = PrinterTaskMappingForm(request.POST, instance=mapping)
        if form.is_valid():
            form.save()
            messages.success(request, f"Task mapping '{mapping.get_task_name_display()}' updated successfully!")
            return redirect('task_printer_mapping')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PrinterTaskMappingForm(instance=mapping)

    return render(request, 'printer/edit_task_mapping.html', {'form': form, 'mapping': mapping})


@login_required(login_url='login')
def delete_task_mapping(request, pk):
    """Delete a task mapping"""
    mapping = get_object_or_404(PrinterTaskMapping, pk=pk)

    if request.method == 'POST':
        task_name = mapping.get_task_name_display()
        mapping.delete()
        messages.success(request, f"Task mapping '{task_name}' deleted successfully!")
        return redirect('task_printer_mapping')

    return render(request, 'printer/delete_task_mapping.html', {'mapping': mapping})


@login_required(login_url='login')
def toggle_task_mapping_status(request, pk):
    """Toggle task mapping active status"""
    mapping = get_object_or_404(PrinterTaskMapping, pk=pk)

    mapping.is_active = not mapping.is_active
    mapping.save()

    status = "activated" if mapping.is_active else "deactivated"
    messages.success(request, f"Task mapping '{mapping.get_task_name_display()}' {status}")

    return redirect('task_printer_mapping')


@login_required(login_url='login')
def quick_assign_printer(request, pk):
    """Quick assign printer to task via AJAX"""
    if request.method == 'POST':
        mapping = get_object_or_404(PrinterTaskMapping, pk=pk)
        printer_id = request.POST.get('printer_id')

        if printer_id:
            printer = get_object_or_404(PrinterConfiguration, pk=printer_id)
            mapping.printer = printer
            mapping.save()

            return JsonResponse({
                'success': True,
                'message': f'Printer updated to {printer.name}'
            })
        else:
            mapping.printer = None
            mapping.save()

            return JsonResponse({
                'success': True,
                'message': 'Printer removed from task'
            })

    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)
