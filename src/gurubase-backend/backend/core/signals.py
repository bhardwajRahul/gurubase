import logging
import os
import requests
from django.db.models.signals import pre_delete, post_delete, post_save, pre_save
from django.conf import settings
from django.dispatch import receiver
from accounts.models import User
from core.utils import embed_text, generate_og_image, draw_text
from core import milvus_utils
from core.models import GithubFile, GuruType, Question, RawQuestion, DataSource

from PIL import ImageColor
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from urllib.parse import urlparse
import secrets
from .models import Integration, APIKey

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Question)
def save_question_to_typesense(sender, instance: Question, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    if settings.TYPESENSE_API_KEY == "xxx":
        return
    curr_sitemap = instance.add_to_sitemap
    try:
        guru_type = instance.guru_type.slug
    except Exception as e:
        logger.error(f"Question {instance.id} does not have a guru_type. Writing/deleting to/from TypeSense skipped.", exc_info=True)
        return
    
    if not guru_type:
        logger.error(f"Question {instance.id} does not have a guru_type. Writing/deleting to/from TypeSense skipped.")
        return

    from core.typesense_utils import TypeSenseClient
    from typesense.exceptions import ObjectNotFound
    typesense_client = TypeSenseClient(guru_type)
    if curr_sitemap:
        # Question is in sitemap
        # Upsert the question to TypeSense
        doc = {
            'id': str(instance.id),
            'slug': instance.slug,
            'question': instance.question,
            # 'content': instance.content,
            # 'description': instance.description,
            # 'change_count': instance.change_count,
        }
        try:
            response = typesense_client.import_documents([doc])
            logger.info(f"Upserted question {instance.id} to Typesense")
        except Exception as e:
            logger.error(f"Error writing question {instance.id} to Typesense: {e}", exc_info=True)

    else:
        # Question is not in sitemap
        # Delete it from TypeSense
        try:
            response = typesense_client.delete_document(str(instance.id))
            logger.info(f"Deleted question {instance.id} from Typesense")
        except ObjectNotFound:
            pass
        except Exception as e:
            logger.error(f"Error deleting question {instance.id} from Typesense: {e}", exc_info=True)

@receiver(post_save, sender=Question)
def generate_og_image_for_new_question(sender, instance, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    if settings.OG_IMAGE_GENERATE and instance.og_image_url=='':
        url, success = generate_og_image(instance)
        if not success:
            logger.error(f'Failure generating og images for new question with id={instance.id} : {url}')
        else:
            logger.info(f'Generated og image at {url}')

@receiver(post_delete, sender=Question)
def delete_og_image(sender, instance, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    if settings.OG_IMAGE_GENERATE and instance.og_image_url!='':
        from core.gcp import OG_IMAGES_GCP
        target_path = instance.og_image_url
        target_path = '/'.join(instance.og_image_url.split('/')[-2:])
        target_path =  f'./{settings.ENV}/{target_path}'
        logger.info(f'delete_og_image {target_path}')
        success = OG_IMAGES_GCP.delete_image(instance.id,target_path)
        if not success:
            logger.error(f'Failed to delete og_image of question with id={instance.id}')

# if you delete the question, delete it from the TypeSense index
@receiver(post_delete, sender=Question)
def delete_question_from_typesense(sender, instance: Question, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    try:
        guru_type = instance.guru_type.slug
    except Exception as e:
        logger.error(f"Question {instance.id} does not have a guru_type. Deleting from TypeSense skipped.", exc_info=True)
        return
    
    if not guru_type:
        logger.error(f"Question {instance.id} does not have a guru_type. Deleting from TypeSense skipped.", exc_info=True)
        return

    from core.typesense_utils import TypeSenseClient
    from typesense.exceptions import ObjectNotFound
    typesense_client = TypeSenseClient(guru_type)
    try:
        response = typesense_client.delete_document(str(instance.id))
    except ObjectNotFound:
        pass
    except Exception as e:
        logger.error(f"Error deleting question {instance.id} from Typesense: {e}", exc_info=True)


@receiver(post_save, sender=GuruType)
def create_base_og_image_for_guru(sender, instance: GuruType, created, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    if instance.ogimage_base_url:
        return

    if not instance.colors:
        logger.error(f'GuruType {instance.slug} has no colors')
        return

    icon_url = instance.icon_url
    if not icon_url:
        logger.error(f'GuruType {instance.slug} has no icon_url')
        return
    
    from PIL import Image, ImageDraw, ImageFont, ImageColor
    from io import BytesIO
    import requests
    from core.gcp import OG_IMAGES_GCP
    
    try:
        template_path = os.path.join(settings.STATICFILES_DIRS[0], 'backend', 'images', 'gurubase-og-image-guru-type.jpg')
        template = Image.open(template_path).convert("RGBA")

        base_color_rgb = ImageColor.getrgb(instance.colors['base_color'])
        draw_template = ImageDraw.Draw(template)

        section_x_start = 0  
        section_x_end = 456 * 2

        draw_template.rectangle(
            [section_x_start,  562 - 44 * 2, section_x_end, 562 + 44 * 2], 
            fill=(base_color_rgb[0], base_color_rgb[1], base_color_rgb[2], 255)
        )

        response = requests.get(icon_url, timeout=30)
        response.raise_for_status()
        import cairosvg

        if response.headers['Content-Type'] == 'image/svg+xml':
            # Convert SVG bytes to PNG bytes
            png_bytes = cairosvg.svg2png(bytestring=response.content)
            image = Image.open(BytesIO(png_bytes)).convert("RGBA")
        else:
            # Assume it's a format supported directly by PIL
            image = Image.open(BytesIO(response.content)).convert("RGBA")
    
        corner_radius = 15

        # Load and resize icon
        icon_image_size = (80, 80)
        image.thumbnail(icon_image_size, Image.Resampling.LANCZOS)
        
        # Create rounded icon with white background in one step
        icon_with_bg = Image.new('RGBA', image.size, (255, 255, 255, 255))
        icon_with_bg.paste(image, (0, 0), image)
        
        # Create and apply rounded mask
        mask = Image.new('L', image.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle([(0, 0), image.size], corner_radius, fill=255)
        icon_with_bg.putalpha(mask)
        
        # Create final white background with padding
        white_background = Image.new('RGBA', (100, 100), (255, 255, 255, 255))
        
        # Center icon on white background
        offset = ((100 - image.size[0]) // 2, (100 - image.size[1]) // 2)
        white_background.paste(icon_with_bg, offset, icon_with_bg)
        
        # Apply rounded corners to final background
        final_mask = Image.new('L', (100, 100), 0)
        draw_mask = ImageDraw.Draw(final_mask)
        draw_mask.rounded_rectangle([(0, 0), (100, 100)], corner_radius, fill=255)
        white_background.putalpha(final_mask)

        icon_x = 24 * 2
        icon_y = 562 - 44 * 2 + 24 * 2
        icon_position = (icon_x, icon_y)

        template.paste(white_background, icon_position, white_background)

        font_filename = 'fonts/gilroy-semibold.ttf'
        font_path = os.path.join(settings.STATICFILES_DIRS[0], 'backend', font_filename)
        
        text = instance.name + ' Guru'
        text_y = icon_y
        text_x = icon_x + white_background.width + 12 * 2
        max_width = section_x_end - text_x - 24 * 2  # Reduce by margin

        # Start with a large font size and decrease if necessary    
        initial_font_size = 88
        for font_size in range(initial_font_size, 10, -2):  # Decrement font size
            guru_font = ImageFont.truetype(font_path, font_size)
            text_y = icon_y + (white_background.size[1] - guru_font.getbbox(text)[3]) // 2
            text_width, _ = guru_font.getbbox(text)[2], guru_font.getbbox(text)[3]
            if text_width <= max_width:
                break  # Font fits within the width
        
        draw_text(draw_template, text_x, text_y, text, guru_font, max_width, 0, (255, 255, 255))

        modified_template_path = 'path_to_save_modified_template.png'
        template.save(modified_template_path)

        folder = settings.ENV
        gcpTargetPath = f'./{folder}/custom-base-templates/{instance.slug}.jpg'
        logger.debug(f'gcp target path for base og image: {gcpTargetPath}')
        
        with open(modified_template_path, 'rb') as f:
            url, success = OG_IMAGES_GCP.upload_image(f, gcpTargetPath)

        if not success:
            logger.error(f'Failed to upload og image for custom guru type {instance.slug}')
        else:
            publicly_accessible_persistent_url = url.split('?', 1)[0]
            instance.ogimage_base_url = publicly_accessible_persistent_url

        os.remove(modified_template_path)
        instance.save()
        
    except Exception as e:
        logger.error(f'Error in creating base og image for guru: {e}', exc_info=True)


@receiver(post_save, sender=GuruType)
def create_question_og_image_for_guru(sender, instance: GuruType, created, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    if instance.ogimage_url:
        return

    icon_url = instance.icon_url
    if icon_url is None or icon_url == '':
        logger.error(f'GuruType {instance.slug} has no icon_url')
        return

    if not instance.colors:
        logger.error(f'GuruType {instance.slug} has no colors')
        return

    try:
        response = requests.get(icon_url, timeout=30)
        if response.status_code != 200:
            logger.error(f'Failed to fetch icon image for custom guru type {instance.slug}')
            return
        
        from PIL import Image, ImageDraw, ImageFont
        from io import BytesIO
        import cairosvg
        from core.gcp import OG_IMAGES_GCP

        if response.headers['Content-Type'] == 'image/svg+xml':
            png_bytes = cairosvg.svg2png(bytestring=response.content)
            image = Image.open(BytesIO(png_bytes)).convert("RGBA")
        else:
            image = Image.open(BytesIO(response.content)).convert("RGBA")

        # Load and resize icon
        icon_image_size = (140, 140)
        image.thumbnail(icon_image_size, Image.Resampling.LANCZOS)
        
        # Create rounded icon with white background in one step
        icon_with_bg = Image.new('RGBA', image.size, (255, 255, 255, 255))
        icon_with_bg.paste(image, (0, 0), image)
        
        # Create and apply rounded mask
        corner_radius = 20
        mask = Image.new('L', image.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle([(0, 0), image.size], corner_radius, fill=255)
        icon_with_bg.putalpha(mask)
        
        # Create final white background with padding
        white_background = Image.new('RGBA', (160, 160), (255, 255, 255, 255))
        
        # Center icon on white background
        offset = ((160 - image.size[0]) // 2, (160 - image.size[1]) // 2)
        white_background.paste(icon_with_bg, offset, icon_with_bg)
        
        # Apply rounded corners to final background
        final_mask = Image.new('L', (160, 160), 0)
        draw_mask = ImageDraw.Draw(final_mask)
        draw_mask.rounded_rectangle([(0, 0), (160, 160)], corner_radius, fill=255)
        white_background.putalpha(final_mask)

        # Fetch the default OG image
        template_path = os.path.join(settings.STATICFILES_DIRS[0], 'backend', 'images', '0_default_og_image.jpg')
        template = Image.open(template_path)

        # Draw the far right section
        base_color_rgb = ImageColor.getrgb(instance.colors['base_color'])
        draw = ImageDraw.Draw(template)
        section_x_start = template.width - 228*2
        section_x_end = template.width
        draw.rectangle(
            [section_x_start, 0, section_x_end, 562*2],
            fill=(base_color_rgb[0], base_color_rgb[1], base_color_rgb[2], 255)
        )

        # Calculate position to paste the white background centered in the colored section
        icon_x = section_x_start + (228*2 - white_background.size[0]) // 2
        icon_y = (562*2 - ((white_background.size[1]//2)+2*2*28)) // 2

        # Paste the white background with icon
        template.paste(white_background, (icon_x, icon_y), white_background)

        font_filename = 'fonts/gilroy-semibold.ttf'
        font_path = os.path.join(settings.STATICFILES_DIRS[0], 'backend', font_filename)

        guru_font = ImageFont.truetype(font_path, 2*28) 

        # Draw the text under the icon

        # center the text to the icon
        text = instance.name
        text_y = icon_y + 160 + 2*10
        t = draw.textlength(text, font=guru_font)
        if t//2 > 80:
            text_x = icon_x - (t//2 - 80)
        else:
            text_x = icon_x + (80 - t//2)

        max_width = 228*2 - (text_x - section_x_start)
        # Start with a large font size and decrease if necessary    
        initial_font_size = 2*28
        for font_size in range(initial_font_size, 10, -2):  # Decrement font size
            guru_font = ImageFont.truetype(font_path, font_size)
            text_width, _ = guru_font.getbbox(text)[2], guru_font.getbbox(text)[3]
            if text_width <= 228*2:
                # t = draw.textlength(text, font=guru_font)
                if text_width//2 > 80:
                    text_x = icon_x - (text_width//2 - 80)
                else:
                    text_x = icon_x + (80 - text_width//2)
                break  # text fits within the width
            
            if text_width//2 > 80:
                text_x = icon_x - (text_width//2 - 80)
            else:
                text_x = icon_x + (80 - text_width//2)
            
            if text_x < section_x_start:
                continue        
        
        draw_text(draw, text_x, text_y, text, guru_font, max_width, 0, (255, 255, 255))

        text = "Guru"
        text_y = text_y + 2*28 
        
        t = draw.textlength(text, font=guru_font)
        if t//2 > 80:
            text_x = icon_x - (t//2 - 80)
        else:
            text_x = icon_x + (80 - t//2)
        draw_text(draw, text_x, text_y, text, guru_font, 228*2 - (text_x - section_x_start), 0, (255, 255, 255))

        # Save the modified template back to a file
        modified_template_path = 'path_to_save_modified_template.png'
        template.save(modified_template_path)

        folder = settings.ENV
        gcpTargetPath = f'./{folder}/custom-templates/{instance.slug}.jpg'
        logger.debug(f'gcp target path: {gcpTargetPath}')
        url, success = OG_IMAGES_GCP.upload_image(open(modified_template_path, 'rb'), gcpTargetPath)
        if not success:
            logger.error(f'Failed to upload og image for custom guru type {instance.slug}')
        else:
            publicly_accessible_persistent_url = url.split('?', 1)[0]
            instance.ogimage_url = publicly_accessible_persistent_url
        
        os.remove(modified_template_path)
        instance.save()
    except Exception as e:
        logger.error(f'Error in creating og image for guru: {e}', exc_info=True)

@receiver(post_delete, sender=Question)
def check_sitemap_upon_question_deletion(sender, instance: Question, **kwargs):
    """
    If a question is deleted, check the other questions that are not added to sitemap because of this question.
    """
    
    # If a question is not added to sitemap because of this question, check it again
    sitemap_check_questions = Question.objects.filter(add_to_sitemap=False, sitemap_reason__contains=f"Similar to question ID: ({instance.id})")
    for question in sitemap_check_questions:
        add_to_sitemap, sitemap_reason = question.is_on_sitemap()
        question.add_to_sitemap = add_to_sitemap
        question.sitemap_reason = sitemap_reason
        question.save()
    

@receiver(post_save, sender=GuruType)
def create_raw_questions_if_not_exist(sender, instance: GuruType, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    if instance.custom:
        return

    raw_questions = RawQuestion.objects.filter(guru_type=instance)
    if not raw_questions:
        raw_question = RawQuestion(guru_type=instance)
        raw_question.save()
        logger.info(f"Created raw question for {instance.slug}")


@receiver(pre_delete, sender=GuruType)
def delete_typesense_collection(sender, instance: GuruType, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    try:
        guru_type = instance.slug
    except Exception as e:
        logger.error(f"GuruType {instance.id} does not have a name. Deleting from TypeSense skipped.", exc_info=True)
        return
    
    if not guru_type:
        logger.error(f"GuruType {instance.id} does not have a name. Deleting from TypeSense skipped.", exc_info=True)
        return

    from core.typesense_utils import TypeSenseClient
    from typesense.exceptions import ObjectNotFound
    typesense_client = TypeSenseClient(guru_type)
    try:
        response = typesense_client.delete_collection()
    except ObjectNotFound:
        pass
    except Exception as e:
        logger.error(f"Error deleting collection for {guru_type} from Typesense: {e}", exc_info=True)


@receiver(post_save, sender=Question)
def save_question_to_milvus(sender, instance: Question, **kwargs):
    if instance.source not in [Question.Source.SUMMARY_QUESTION, Question.Source.RAW_QUESTION]:
        return

    if instance.binge:
        return

    if settings.ENV == 'selfhosted':
        return
    
    questions_collection_name = settings.MILVUS_QUESTIONS_COLLECTION_NAME
    if not milvus_utils.collection_exists(collection_name=questions_collection_name):
        milvus_utils.create_similarity_collection(questions_collection_name)

    # Check existence
    question_in_milvus = milvus_utils.fetch_vectors(questions_collection_name, f'id=={instance.id}', output_fields=['id', 'on_sitemap'])
    if question_in_milvus:
        # If add_to_sitemap changed, delete the old vector and reinsert
        if instance.add_to_sitemap != question_in_milvus[0]["on_sitemap"]:
            milvus_utils.delete_vectors(questions_collection_name, [str(instance.id)])
        else:
            logger.warning(f'Question {instance.id} already exists and is not changing add_to_sitemap in Milvus. Skipping...')
            return

    doc = {
        'title': instance.question,
        'slug': instance.slug,
        'id': instance.id,
        'on_sitemap': instance.add_to_sitemap,
        'guru_type': instance.guru_type.slug,
    }
    
    title_embedding = embed_text(instance.question)
    if not title_embedding:
        logger.error(f'Could not embed the title of question {instance.id}')
        return

    # description_embedding = embed_text(instance.description)
    # if not description_embedding:
    #     logger.error(f'Could not embed the description of question {instance.id}')
    #     return

    content_embedding = embed_text(instance.content)
    if not content_embedding:
        logger.error(f'Could not embed the content of question {instance.id}')
        return

    # doc['description_vector'] = description_embedding
    doc['description_vector'] = [0] * settings.MILVUS_CONTEXT_COLLECTION_DIMENSION
    doc['title_vector'] = title_embedding
    doc['content_vector'] = content_embedding
    
    milvus_utils.insert_vectors(
        collection_name=questions_collection_name,
        docs=[doc]
    )
    logger.info(f'Inserted question {instance.id} back into Milvus')


@receiver(pre_delete, sender=Question)
def delete_question_from_milvus(sender, instance: Question, **kwargs):
    questions_collection_name = settings.MILVUS_QUESTIONS_COLLECTION_NAME
    if not milvus_utils.collection_exists(collection_name=questions_collection_name):
        return

    if settings.ENV == 'selfhosted':
        return

    try:
        milvus_utils.delete_vectors(
            collection_name=questions_collection_name,
            ids=[str(instance.id)]
        )
    except Exception as e:
        logger.error(f"Error deleting question {instance.id} from Milvus: {e}", exc_info=True)


# @receiver(pre_save, sender=Question)
# def decide_if_english(sender, instance: Question, **kwargs): 
#     if instance.id:
#         return

#     instance.english, usages = ask_if_english(instance.question)
#     del usages['price_eval_success']
#     instance.llm_usages['english_check'] = usages

# @receiver(pre_save, sender=Question)
# def add_to_sitemap_if_possible(sender, instance: Question, **kwargs):
#     # Skip if question is already created
#     if instance.id:
#         return
#     add_to_sitemap, sitemap_reason = instance.is_on_sitemap()
#     instance.add_to_sitemap = add_to_sitemap
#     instance.sitemap_reason = sitemap_reason


@receiver(pre_delete, sender=DataSource)
def clear_data_source(sender, instance: DataSource, **kwargs):
    logger.info(f"Clearing data source: {instance.id}")
    if instance.type == DataSource.Type.PDF and instance.url:
        if settings.STORAGE_TYPE == 'gcloud':
            from core.gcp import DATA_SOURCES_GCP
            endpoint = instance.url.split('/', 4)[-1]
            DATA_SOURCES_GCP.delete_file(endpoint)
        else:
            try:
                os.remove(instance.url)
            except Exception as e:
                logger.error(f"Error deleting local file: {e}", exc_info=True)

    if instance.in_milvus:
        instance.delete_from_milvus()

    if instance.type == DataSource.Type.GITHUB_REPO:
        GithubFile.objects.filter(data_source=instance).delete()


@receiver(post_save, sender=GuruType)
def create_milvus_collection(sender, instance: GuruType, created, **kwargs):
    collection_name = instance.milvus_collection_name
    if created and not milvus_utils.collection_exists(collection_name=collection_name):
        milvus_utils.create_context_collection(collection_name)


@receiver(pre_save, sender=GuruType)
def rename_milvus_collection(sender, instance: GuruType, **kwargs):
    if instance.id:  # This is an update
        try:
            old_instance = GuruType.objects.get(id=instance.id)
            if old_instance.slug != instance.slug:
                old_collection_name = old_instance.milvus_collection_name
                new_collection_name = instance.milvus_collection_name
                if milvus_utils.collection_exists(collection_name=old_collection_name):
                    logger.info(f"Renaming Milvus collection from {old_collection_name} to {new_collection_name}")
                    milvus_utils.rename_collection(old_collection_name, new_collection_name)
                else:
                    logger.warning(f"Milvus collection {old_collection_name} does not exist, skipping rename operation")
        except GuruType.DoesNotExist:
            logger.error(f"GuruType instance with id {instance.id} not found")


@receiver(pre_save, sender=GuruType)
def rename_question_guru_types(sender, instance: GuruType, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    if instance.id:  # This is an update
        try:
            old_instance = GuruType.objects.get(id=instance.id)
            if old_instance.slug != instance.slug:
                collection_name = settings.MILVUS_QUESTIONS_COLLECTION_NAME
                # Update all questions with the old guru type to the new guru type in milvus
                questions = milvus_utils.fetch_vectors(collection_name, f'guru_type=="{old_instance.slug}"')
                
                for question in questions:
                    question['guru_type'] = instance.slug

                milvus_utils.upsert_vectors(collection_name, questions)
        except GuruType.DoesNotExist:
            logger.error(f"GuruType instance with id {instance.id} not found")


@receiver(post_save, sender=Question)
def notify_new_user_question(sender, instance: Question, created, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    if created and instance.source in [Question.Source.USER, Question.Source.WIDGET_QUESTION] and settings.SLACK_NOTIFIER_ENABLED:
        question_url = f"{settings.BASE_URL}/g/{instance.guru_type.slug}/{instance.slug}"
        message = f"Title: {instance.question}\nURL: {question_url}\nUser Question: {instance.user_question}\nSource: {instance.source}"

        if instance.user:
            message += f"\nUser Email: {instance.user.email}"
        else:
            message += f"\nUser: Anonymous"
        
        webhook_url = settings.SLACK_NOTIFIER_WEBHOOK_URL
        payload = {"text": message}
        
        try:
            response = requests.post(webhook_url, json=payload, timeout=30)
            response.raise_for_status()
            logger.info(f"Slack notification sent for new question: {instance.id}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Slack notification for question {instance.id}: {str(e)}", exc_info=True)


@receiver(post_save, sender=User)
def notify_new_user(sender, instance: User, created, **kwargs):
    if settings.ENV == 'selfhosted':
        return

    if created and settings.SLACK_NOTIFIER_ENABLED:
        message = f"⚡️ New user signed up: {instance.email} ({instance.name}) via {instance.auth_provider}"
        
        webhook_url = settings.SLACK_NOTIFIER_WEBHOOK_URL
        payload = {"text": message}
        
        try:
            response = requests.post(webhook_url, json=payload, timeout=30)
            response.raise_for_status()
            logger.info(f"Slack notification sent for new user: {instance.email}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Slack notification for user {instance.email}: {str(e)}", exc_info=True)


@receiver(pre_save, sender=DataSource)
def update_data_source_in_milvus(sender, instance: DataSource, **kwargs):
    # If 
    # - The data source is being updated
    # - The title of the data source is changed
    # - The data source is written to milvus and has document ids
    # Then we need to update the vector in milvus

    # Return it newly created
    if not instance.id:
        return

    if instance.type == DataSource.Type.GITHUB_REPO:
        return

    # Cases:
    # 1- New creation
    # 2- Not written to milvus
    #   2-a. Title changed
    #   2-b. Title not changed
    # 3- Written to milvus
    #   3-a. Title changed
    #   3-b. Title not changed

    # Each doc is of format
    # {
    #     "metadata": {
    #         "type": type,
    #         "link": link,
    #         "split_num": split_num,
    #         "title": title,
    #     },
    #     "text": split,
    #     "vector": embeddings[i],
    # }
    
    # Get the old title
    old_instance = DataSource.objects.get(id=instance.id)

    title_changed = old_instance.title != instance.title
    if title_changed and instance.in_milvus and instance.doc_ids:
        collection_name = instance.guru_type.milvus_collection_name
        if milvus_utils.collection_exists(collection_name=collection_name):
            docs = milvus_utils.fetch_vectors(collection_name, f'metadata["link"] == "{instance.url}"')
            for doc in docs:
                doc['metadata']['title'] = instance.title
                
            # Remove the old vectors
            milvus_utils.delete_vectors(collection_name, [str(doc['id']) for doc in docs])

            for doc in docs:
                del doc['id']

            # Insert the new vectors
            ids = milvus_utils.insert_vectors(collection_name, docs)
            instance.doc_ids = list(ids)

@receiver(pre_delete, sender=GuruType)
def delete_guru_type_questions(sender, instance: GuruType, **kwargs):
    """Delete all questions associated with a guru type when it's deleted"""
    try:
        Question.objects.filter(guru_type=instance).delete()
        logger.info(f"Deleted all questions for guru type: {instance.slug}")
    except Exception as e:
        logger.error(f"Error deleting questions for guru type {instance.slug}: {e}", exc_info=True)


@receiver(pre_delete, sender=GithubFile)
def clear_github_file(sender, instance: GithubFile, **kwargs):
    if instance.in_milvus:
        logger.info(f"Clearing github file: {instance.id}")
        instance.delete_from_milvus()

@receiver(pre_save, sender=GuruType)
def validate_github_repo(sender, instance, **kwargs):
    """Validate GitHub repo URL format if provided"""
    if instance.github_repo:
        # Normalize URL by removing trailing slash
        instance.github_repo = instance.github_repo.rstrip('/')
        
        # Validate URL format
        url_validator = URLValidator()
        try:
            url_validator(instance.github_repo)
        except ValidationError:
            raise ValidationError({'msg': 'Invalid URL format'})

        # Ensure it's a GitHub URL
        parsed_url = urlparse(instance.github_repo)
        if not parsed_url.netloc.lower() in ['github.com', 'www.github.com']:
            raise ValidationError({'msg': 'URL must be a GitHub repository'})
            
        # Ensure it has a path (repository)
        if not parsed_url.path or parsed_url.path == '/':
            raise ValidationError({'msg': 'Invalid GitHub repository URL'})

        # Ensure URL has valid scheme
        if parsed_url.scheme not in ['http', 'https']:
            raise ValidationError({'msg': 'URL must start with http:// or https://'})

@receiver(post_save, sender=GuruType)
def manage_github_repo_datasource(sender, instance, **kwargs):
    from core.tasks import data_source_retrieval
    """Manage DataSource based on github_repo and index_repo fields"""
    existing_datasource = DataSource.objects.filter(
        guru_type=instance,
        type=DataSource.Type.GITHUB_REPO,
    ).first()

    # Case 1: URL exists and index_repo is True - Create/Update DataSource
    if instance.github_repo and instance.index_repo:
        if existing_datasource:
            if existing_datasource.url != instance.github_repo:
                # URL changed - delete old and create new
                existing_datasource.delete()
                DataSource.objects.create(
                    guru_type=instance,
                    type=DataSource.Type.GITHUB_REPO,
                    url=instance.github_repo,
                    status=DataSource.Status.NOT_PROCESSED
                )
        else:
            # No existing datasource - create new
            DataSource.objects.create(
                guru_type=instance,
                type=DataSource.Type.GITHUB_REPO,
                url=instance.github_repo,
                status=DataSource.Status.NOT_PROCESSED
            )

        data_source_retrieval.delay(guru_type_slug=instance.slug)

    # Case 2: Either URL is empty or index_repo is False - Delete DataSource
    elif existing_datasource:
        existing_datasource.delete()

@receiver(post_save, sender=DataSource)
def data_source_retrieval_on_creation(sender, instance: DataSource, created, **kwargs):
    from core.tasks import data_source_retrieval

    if created and instance.status == DataSource.Status.NOT_PROCESSED:
        data_source_retrieval.delay(guru_type_slug=instance.guru_type.slug)

@receiver(pre_save, sender=Integration)
def create_api_key_for_integration(sender, instance, **kwargs):
    if not instance.api_key_id:
        api_key = APIKey.objects.create(
            user=instance.guru_type.maintainers.first(),
            key=secrets.token_urlsafe(32),
            integration=True
        )
        instance.api_key = api_key

@receiver(pre_delete, sender=Integration)
def delete_api_key_for_integration(sender, instance, **kwargs):
    if instance.api_key:
        instance.api_key.delete()