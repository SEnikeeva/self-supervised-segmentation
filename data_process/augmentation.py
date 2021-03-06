from torchvision import transforms


class DataAugmentation:

    def __init__(self, crop_size=100):
        self.aug_methods = transforms.Compose(
            [
                transforms.RandomResizedCrop(crop_size),
                transforms.RandomHorizontalFlip(),
            ]
        )

    def __call__(self, img):
        return self.aug_methods(img)


class PretrainAugmentation:

    def __init__(self, crop_size=100):
        self.aug_methods = transforms.Compose(
            [
                transforms.RandomResizedCrop(crop_size),
                transforms.RandomApply([transforms.ColorJitter(0.4, 0.4, 0.4, 0.1)], p=0.),
                transforms.RandomGrayscale(p=0.2),
                transforms.RandomApply([transforms.GaussianBlur(1)], p=0.),
                transforms.RandomHorizontalFlip(),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ]
        )

    def __call__(self, img):
        """
        :param img: input image
        :return: two random augmented views of one image.
        """
        return [self.aug_methods(img), self.aug_methods(img)]


class TargetAugmentation:

    def __init__(self, crop_size=100):
        self.aug_methods = transforms.Compose(
            [
                transforms.RandomResizedCrop(crop_size),
                transforms.RandomHorizontalFlip(),
            ]
        )

    def __call__(self, img):
        return self.aug_methods(img)
