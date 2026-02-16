"""
Printer Management Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import PrinterConfiguration, PrintJob, PrinterTaskMapping
from .forms import PrinterConfigurationForm, PrinterTaskMappingForm
from .printing import PrinterManager
import logging

logger = logging.getLogger(__name__)


@login_required(login_url='login')
def printer_management(request):
    """Main printer management page"""
    printers = PrinterConfiguration.objects.all()
    recent_jobs = PrintJob.objects.select_related('printer', 'created_by')[:20]

    # Get system printers
    system_printers = PrinterManager.get_system_printers()

    context = {
        'printers': printers,
        'recent_jobs': recent_jobs,
        'system_printers': system_printers,
    }
    return render(request, 'printer/printer_management.html', context)


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
